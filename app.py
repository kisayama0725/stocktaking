import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime, date

# --- 1. スプレッドシートへの接続設定 ---
# 接続を初期化
conn = st.connection("gsheets", type=GSheetsConnection)

def load_master():
    try:
        # masterシートを読み込み
        return conn.read(worksheet="master")
    except:
        return pd.DataFrame(columns=["カテゴリー", "アイテム名", "単位①容量", "集計単位①", "入力単位②", "集計単位②", "換算数値"])

def load_log():
    try:
        # logシートを読み込み
        df = conn.read(worksheet="log")
        if not df.empty and "日付" in df.columns:
            df["日付"] = pd.to_datetime(df["日付"]).dt.date
        return df
    except:
        return pd.DataFrame(columns=["日付", "車両番号", "種別", "アイテム名", "単位①数値", "単位②数値"])

# データの読み込み
df_master = load_master()
df_log = load_log()

# カテゴリーの定義
CATEGORIES = [
    "チーズ", "野菜カット物", "缶詰", "ソース類", "魚介類", 
    "サイド", "添付物", "ドリンク", "解凍物", "グッズその他", 
    "生地", "冷凍食材", "カートン", "その他包材", "厨房備品"
]

# --- 2. サイドバーメニュー ---
st.sidebar.title("🚚 在庫・車両管理")
page = st.sidebar.radio(
    "移動先を選択", 
    ["積み込み", "追加", "積み下ろし", "ロス", "最終集計", "マスター管理", "データ履歴削除"],
    key="nav_menu"
)

st.title(f"【{page}】")

# --- 3. 入力画面 ---
if page in ["積み込み", "追加", "積み下ろし", "ロス"]:
    if df_master.empty:
        st.warning("先にマスター管理でアイテムを登録してください。")
    else:
        c_top1, c_top2 = st.columns(2)
        with c_top1: input_date = st.date_input("日付", value=date.today(), key=f"d_{page}")
        with c_top2: car_id = st.text_input("車両番号", key=f"s_{page}")

        st.divider()
        h1, h2, h3, h4 = st.columns([1.2, 1, 1, 0.8])
        with h1: st.caption("アイテム名")
        with h2: st.caption("単位①")
        with h3: st.caption("単位②")
        with h4: st.caption("操作")

        input_list = []
        for cat in df_master["カテゴリー"].unique():
            st.markdown(f"### {cat}")
            df_cat = df_master[df_master["カテゴリー"] == cat]
            for i, row in df_cat.iterrows():
                item = row["アイテム名"]
                u1_label, u2_label = row["集計単位①"], row["入力単位②"]
                
                with st.container():
                    c1, c2, c3, c4 = st.columns([1.2, 1, 1, 0.8], vertical_alignment="center")
                    with c1: st.write(f"**{item}**")
                    with c2: v1 = st.number_input(f"{u1_label}", min_value=0, step=1, key=f"u1_{page}_{item}", label_visibility="collapsed")
                    with c3: v2 = st.number_input(f"{u2_label}", min_value=0.0, step=0.1, key=f"u2_{page}_{item}", label_visibility="collapsed")
                    with c4:
                        if st.button("登録", key=f"btn_{page}_{item}", use_container_width=True):
                            if not car_id: st.error("車両番号入力")
                            elif v1 > 0 or v2 > 0:
                                new_row = pd.DataFrame([[input_date, car_id, page, item, v1, v2]], columns=df_log.columns)
                                updated_log = pd.concat([df_log, new_row], ignore_index=True)
                                conn.update(worksheet="log", data=updated_log)
                                st.success(f"{item} 保存")
                                st.rerun()
                    input_list.append({"item": item, "v1": v1, "v2": v2})

        st.divider()
        if st.button(f"一括で{page}する", use_container_width=True, type="primary"):
            if not car_id: st.error("車両番号を入力してください")
            else:
                new_rows = [[input_date, car_id, page, d["item"], d["v1"], d["v2"]] for d in input_list if d["v1"] > 0 or d["v2"] > 0]
                if new_rows:
                    new_df = pd.DataFrame(new_rows, columns=df_log.columns)
                    updated_log = pd.concat([df_log, new_df], ignore_index=True)
                    conn.update(worksheet="log", data=updated_log)
                    st.success("一括保存完了")
                    st.rerun()

# --- 4. 最終集計 ---
elif page == "最終集計":
    st.header("📊 集計検索")
    if not df_log.empty:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1: start_d = st.date_input("開始日", date.today().replace(day=1))
        with c2: end_d = st.date_input("終了日", date.today())
        with c3: 
            all_cars = ["すべて"] + sorted(df_log["車両番号"].unique().tolist())
            search_car = st.selectbox("車両番号で絞り込み", all_cars)

        mask = (df_log["日付"] >= start_d) & (df_log["日付"] <= end_d)
        if search_car != "すべて":
            mask = mask & (df_log["車両番号"] == search_car)
        
        df_f = df_log.loc[mask]

        if not df_f.empty:
            df_c = pd.merge(df_f, df_master, on="アイテム名")
            
            def calc_stock_pcs(row):
                conv_unit2 = row["単位②数値"] / row["換算数値"]
                total_pcs = (row["単位①数値"] * row["単位①容量"]) + conv_unit2
                return total_pcs if row["種別"] in ["積み込み", "追加"] else -total_pcs
            
            df_c["個数差分"] = df_c.apply(calc_stock_pcs, axis=1)
            res = df_c.groupby(["カテゴリー", "アイテム名"]).agg({
                "個数差分":"sum", "単位①容量":"first", "集計単位①":"first", "集計単位②":"first"
            }).reset_index()

            def fmt_res(row):
                total = round(row["個数差分"], 1)
                abs_total = abs(total)
                v1 = int(abs_total // row["単位①容量"])
                v2 = int(round(abs_total % row["単位①容量"]))
                prefix = "-" if total < 0 else ""
                return f"{prefix}{v1} {row['集計単位①']} + {v2} {row['集計単位②']}"

            res["現在在庫/差分"] = res.apply(fmt_res, axis=1)
            for cat in res["カテゴリー"].unique():
                st.subheader(f"📁 {cat}")
                st.table(res[res["カテゴリー"] == cat][["アイテム名", "現在在庫/差分"]])
        else:
            st.warning("条件に一致するデータがありません")
    else:
        st.info("データがありません")

# --- 5. マスター管理 ---
elif page == "マスター管理":
    st.header("⚙️ マスター設定")
    with st.form("m_form"):
        m_cat = st.selectbox("カテゴリー", CATEGORIES)
        m_name = st.text_input("アイテム名")
        c1, c2 = st.columns(2)
        with c1: m_u1 = st.text_input("単位①の名称 (袋/CS)", "袋")
        with c2: m_cap = st.number_input("単位①あたりの入り数", 1, value=120)
        c3, c4 = st.columns(2)
        with c3: m_u2_in = st.text_input("入力単位 (g)", "g")
        with c4: m_u2_out = st.text_input("集計単位② (個)", "個")
        m_conv = st.number_input("単位② 1つあたりの実測数値", min_value=0.01, value=6.7, step=0.1)
        
        if st.form_submit_button("マスター登録"):
            if m_name:
                new_m = pd.DataFrame([[m_cat, m_name, m_cap, m_u1, m_u2_in, m_u2_out, m_conv]], columns=df_master.columns)
                updated_master = pd.concat([df_master, new_m], ignore_index=True)
                conn.update(worksheet="master", data=updated_master)
                st.success(f"{m_name}を登録しました")
                st.rerun()

    st.divider()
    if not df_master.empty:
        st.subheader("登録済みリスト")
        st.dataframe(df_master, use_container_width=True)
        del_item = st.selectbox("削除するアイテムを選択", df_master["アイテム名"])
        if st.button("選択したアイテムを削除"):
            updated_master = df_master[df_master["アイテム名"] != del_item]
            conn.update(worksheet="master", data=updated_master)
            st.rerun()

# --- 6. 履歴削除 ---
elif page == "データ履歴削除":
    st.header("🗑️ 履歴削除")
    if not df_log.empty:
        st.dataframe(df_log, use_container_width=True)
        del_idx = st.number_input("削除したい行番号を入力", 0, len(df_log)-1, step=1)
        if st.button("行を削除する"):
            updated_log = df_log.drop(df_log.index[del_idx])
            conn.update(worksheet="log", data=updated_log)
            st.rerun()
