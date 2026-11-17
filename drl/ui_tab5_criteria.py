"""TAB 5 – Quản lý Quy chế ĐRL (hcmus.drl.vn Rules Management)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import config, database, seed_data
from . import ui_common as ui


def render() -> None:
    ui.hero(
        "📜 Quản lý Quy chế ĐRL HCMUS",
        "Danh mục tiêu chí · điểm tối đa · điều kiện bắt buộc · minh chứng cần có · "
        "trích dẫn quy chế. Đồng bộ từ hcmus.drl.vn qua Chrome Extension hoặc nhập tay.",
    )
    criteria = database.get_criteria()
    if criteria.empty:
        ui.note_box(
            "Danh mục tiêu chí đang trống. Nạp **khung tiêu chí theo Quy chế ĐRL** để "
            "app tính được điểm tối đa và lộ trình; sau đó **đối chiếu điểm từng tiêu chí "
            "với quy chế chính thức** tại https://hcmus.drl.vn/ (hoặc để Chrome Extension "
            "đồng bộ bảng điểm thật của bạn)."
        )
        if st.button("📜 Nạp khung tiêu chí theo Quy chế ĐRL", type="primary", key="load_rule_framework"):
            n = 0
            for crit in seed_data.DEMO_CRITERIA:
                database.upsert_criterion({**crit, "is_demo": False})
                n += 1
            database.log_action("LOAD_RULE_FRAMEWORK", {"count": n})
            st.success(f"Đã nạp {n} tiêu chí theo khung quy chế.")
            st.rerun()
        return

    total_max = float(criteria["max_score"].sum())
    mandatory = criteria[criteria["mandatory"] == 1]
    c1, c2, c3 = st.columns(3)
    c1.metric("Số tiêu chí", len(criteria))
    c2.metric("Tổng điểm tối đa", f"{total_max:g}")
    c3.metric("Tiêu chí bắt buộc", len(mandatory),
              help=", ".join(mandatory["code"]) if len(mandatory) else "Không có")

    if abs(total_max - 100) > 0.01:
        ui.warn_box(
            f"Tổng điểm tối đa các tiêu chí hiện là **{total_max:g}**, không bằng 100. "
            "Hãy kiểm tra lại quy chế trước khi dùng để tính lộ trình."
        )
    if (criteria["is_demo"] == 1).all():
        ui.note_box(
            "Danh mục tiêu chí lấy từ **khung quy chế** (chưa đồng bộ từ tài khoản của bạn). "
            "Điểm tối đa và trích dẫn cần đối chiếu với quy chế chính thức trên "
            "https://hcmus.drl.vn/."
        )

    st.subheader("📋 Danh mục tiêu chí hiện hành")
    display = criteria.copy()
    display["mandatory"] = display["mandatory"].apply(lambda v: "✅ Bắt buộc" if ui.to_int(v) else "—")
    display = display.drop(columns=["is_demo"], errors="ignore")
    display.columns = ["ID", "Mã", "Tên tiêu chí", "Nhóm", "Điểm tối đa", "Bắt buộc",
                       "Minh chứng cần có", "Trích dẫn quy chế", "Cập nhật"]
    st.dataframe(display, width="stretch", hide_index=True, height=390)
    ui.download_csv_button(criteria, "drl_criteria_hcmus.csv",
                           "⬇️ Xuất danh mục tiêu chí (CSV)", "dl_criteria")

    st.divider()
    tab_view, tab_add, tab_edit, tab_upload = st.tabs([
        "👁️ Xem chi tiết", "➕ Thêm tiêu chí", "✏️ Sửa / Xoá", "⬆️ Nhập hàng loạt (CSV/JSON)",
    ])

    with tab_view:
        pick = st.selectbox("Chọn tiêu chí", list(criteria["code"]), key="crit_view")
        row = criteria[criteria["code"] == pick].iloc[0]
        st.markdown(f"### {row['code']} – {row['name']}")
        st.write(f"**Nhóm:** {row['category'] or '—'}")
        st.write(f"**Điểm tối đa:** {float(row['max_score']):g}")
        st.write(f"**Bắt buộc:** {'Có' if int(row['mandatory']) else 'Không'}")
        st.write(f"**Minh chứng cần có:** {row['evidence_required'] or '—'}")
        st.write(f"**Trích dẫn quy chế:** {row['rule_reference'] or '—'}")
        progress = database.get_criterion_progress(
            database.latest_profile().get("student_id", ""),
            database.latest_profile().get("semester", ""),
        )
        if not progress.empty:
            mine = progress[progress["criterion_code"] == pick]
            if not mine.empty:
                cur = float(mine.iloc[0]["current_score"])
                st.progress(min(1.0, cur / max(1e-9, float(row["max_score"]))),
                            text=f"Tiến độ của bạn: {cur:g}/{float(row['max_score']):g}")

    with tab_add:
        with st.form("add_criterion_form", border=True):
            c1, c2 = st.columns(2)
            code = c1.text_input("Mã tiêu chí *", placeholder="TC_7.1")
            name = c2.text_input("Tên tiêu chí *", placeholder="Hoạt động nghiên cứu khoa học cấp Trường")
            c3, c4, c5 = st.columns(3)
            category = c3.text_input("Nhóm", placeholder="VII. Hoạt động khác")
            max_score = c4.number_input("Điểm tối đa *", 0.0, 100.0, 5.0, 0.5)
            mandatory = c5.checkbox("Bắt buộc")
            evidence = st.text_input("Minh chứng cần có", placeholder="Giấy chứng nhận / danh sách điểm danh")
            rule_ref = st.text_area("Trích dẫn quy chế", height=80,
                                    placeholder="VD: Mục VII.1 – ... (nguồn: hcmus.drl.vn)")
            if st.form_submit_button("💾 Thêm tiêu chí", type="primary"):
                if not code.strip() or not name.strip():
                    st.error("Mã và tên tiêu chí là bắt buộc.")
                elif code.strip() in set(criteria["code"]):
                    st.error("Mã tiêu chí đã tồn tại – dùng tab Sửa để cập nhật.")
                else:
                    database.upsert_criterion({
                        "code": code.strip(), "name": name.strip(), "category": category,
                        "max_score": max_score, "mandatory": mandatory,
                        "evidence_required": evidence, "rule_reference": rule_ref,
                        "is_demo": False,
                    })
                    database.log_action("ADD_CRITERION", {"code": code, "name": name})
                    st.success("Đã thêm tiêu chí.")
                    st.rerun()

    with tab_edit:
        pick_edit = st.selectbox("Chọn tiêu chí cần sửa", list(criteria["code"]), key="crit_edit")
        row = criteria[criteria["code"] == pick_edit].iloc[0]
        with st.form("edit_criterion_form", border=True):
            c1, c2 = st.columns(2)
            name = c1.text_input("Tên tiêu chí", value=row["name"])
            category = c2.text_input("Nhóm", value=row["category"] or "")
            c3, c4, c5 = st.columns(3)
            max_score = c3.number_input("Điểm tối đa", 0.0, 100.0, float(row["max_score"]), 0.5)
            mandatory = c4.checkbox("Bắt buộc", value=bool(ui.to_int(row["mandatory"])))
            c5.write("")
            c5.write("")
            c5.caption(f"Cập nhật: {row['updated_at']}")
            evidence = st.text_input("Minh chứng cần có", value=row["evidence_required"] or "")
            rule_ref = st.text_area("Trích dẫn quy chế", value=row["rule_reference"] or "", height=80)
            col_save, col_del = st.columns([1, 1])
            save = col_save.form_submit_button("💾 Lưu thay đổi", type="primary")
            delete = col_del.form_submit_button("🗑️ Xoá tiêu chí này")
        if save:
            database.upsert_criterion({
                "code": pick_edit, "name": name, "category": category,
                "max_score": max_score, "mandatory": mandatory,
                "evidence_required": evidence, "rule_reference": rule_ref,
                "is_demo": bool(int(row["is_demo"])),
            })
            database.log_action("EDIT_CRITERION", {"code": pick_edit})
            st.success("Đã cập nhật tiêu chí.")
            st.rerun()
        if delete:
            with database.transaction() as conn:
                conn.execute("DELETE FROM DRLCriteria WHERE code = ?", (pick_edit,))
            database.log_action("DELETE_CRITERION", {"code": pick_edit})
            st.warning(f"Đã xoá tiêu chí {pick_edit}. Điểm tiến độ liên quan cần rà soát lại.")
            st.rerun()

    with tab_upload:
        ui.note_box(
            "Hai cách cập nhật quy chế: (1) đồng bộ gói `hcmus_sync.json` từ Chrome Extension ở Tab 1 "
            "(phần `drl_progress` sẽ cập nhật tên + điểm tối đa); (2) nhập file CSV/JSON danh mục tiêu chí bên dưới."
        )
        template = pd.DataFrame([{
            "code": "TC_7.1", "name": "Tên tiêu chí mẫu", "category": "VII. Nhóm mẫu",
            "max_score": 5, "mandatory": 0,
            "evidence_required": "Minh chứng mẫu", "rule_reference": "Mục VII.1 – trích dẫn quy chế",
        }])
        ui.download_csv_button(template, "drl_criteria_template.csv",
                               "⬇️ Tải CSV mẫu", "dl_criteria_tpl")
        uploaded = st.file_uploader("Tải file CSV/Excel danh mục tiêu chí",
                                    type=["csv", "xlsx", "xls"], key="crit_upload")
        if uploaded is not None:
            try:
                df = pd.read_excel(uploaded) if uploaded.name.lower().endswith((".xlsx", ".xls")) \
                    else pd.read_csv(uploaded)
                st.dataframe(df.head(10), width="stretch", height=220)
                required = {"code", "name", "max_score"}
                if not required.issubset(set(df.columns)):
                    st.error(f"File thiếu cột bắt buộc: {sorted(required - set(df.columns))}")
                elif st.button("⬆️ Nhập & ghi đè theo mã tiêu chí", type="primary", key="crit_import"):
                    count = 0
                    for rec in df.to_dict("records"):
                        if not rec.get("code"):
                            continue
                        database.upsert_criterion({
                            "code": str(rec["code"]).strip(),
                            "name": str(rec.get("name") or rec["code"]).strip(),
                            "category": str(rec.get("category") or ""),
                            "max_score": float(rec.get("max_score") or 0),
                            "mandatory": bool(rec.get("mandatory")),
                            "evidence_required": str(rec.get("evidence_required") or ""),
                            "rule_reference": str(rec.get("rule_reference") or ""),
                            "is_demo": False,
                        })
                        count += 1
                    database.log_action("IMPORT_CRITERIA", {"rows": count})
                    st.success(f"Đã nhập/cập nhật {count} tiêu chí.")
                    st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Không đọc được file: {exc}")

        st.divider()
        st.markdown("**Hoặc nạp lại khung tiêu chí theo Quy chế ĐRL:**")
        if st.button("📜 Nạp khung tiêu chí (ghi đè theo mã)", key="reload_rule_framework"):
            for crit in seed_data.DEMO_CRITERIA:
                database.upsert_criterion({**crit, "is_demo": False})
            database.log_action("RELOAD_RULE_FRAMEWORK", {"count": len(seed_data.DEMO_CRITERIA)})
            st.success("Đã nạp lại khung tiêu chí theo quy chế.")
            st.rerun()
