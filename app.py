import streamlit as st
import json
import time
import pandas as pd
import datetime as dt
from pymongo import MongoClient, DESCENDING
import requests
import plotly.express as px


def color_survived(val):
    if val > 0:
        color = "#7FFF00"
    elif val < 0:
        color = "#dc143c"
    return f"color: {color}"


st.markdown(
    "<h2 style='text-align: center; color: white;'>Systematic - Virtual Trading</h2>",
    unsafe_allow_html=True,
)

st.write("-----")

strategy_name = st.selectbox("Select the Strategy", ["SSS"]).lower()

# connect to the database
mongo = MongoClient(st.secrets["mongo_db"]["mongo_url"])
mydb = mongo["test"]
coll = mydb[f"systematic-strategy-{strategy_name}"]


st.write("-----")

df = pd.DataFrame(
    list(coll.find()),
    columns=[
        "trade_date",
        "strike",
        "entry_price",
        "sl_price",
        "qty",
        "entry_time",
        "exit_price",
        "pnl",
        "exit_time",
        "exit_type",
        "pnl_movement",
    ],
)
df = df.set_index("strike")

feature = st.radio(
    "What do you want to analyze?",
    ("Analyze Strategy Statistics", "Analyze a particular day's trade"),
)

if feature == "Analyze a particular day's trade":
    # Datewise PNL
    st.write("----")
    selected_date = str(st.date_input("Select trade date:"))
    st.write("-----")

    df_selected_date = df[df["trade_date"] == selected_date]

    if df_selected_date.shape[0] == 0:
        st.info(f"No Trade on {selected_date}")
    else:
        net_pnl = round(df_selected_date["pnl"].sum(), 2)
        if net_pnl >= 0:
            st.success(f"Net PNL (in pts.): \n {net_pnl}")
        else:
            st.error(f"Net PNL (in pts.): \n {net_pnl}")

    st.write("")

    for i in range(df_selected_date.shape[0]):
        st.table(
            df_selected_date.iloc[
                i,
                [1, 4, 2, 5, 7, 8, 6],
            ].T
        )

        pnl_movement_link = df_selected_date.iloc[i][9]

        st.image(
            pnl_movement_link,
            caption="PNL Movement",
        )

        st.write("---")

else:
    stats_df = df[["trade_date", "pnl"]].groupby(["trade_date"], sort=False).sum()
    stats_df.reset_index(inplace=True)

    # set inital streak values
    stats_df["loss_streak"] = 0
    stats_df["win_streak"] = 0

    if stats_df["pnl"][0] > 0:
        stats_df["loss_streak"][0] = 0
        stats_df["win_streak"][0] = 1

    else:
        stats_df["loss_streak"][0] = 1
        stats_df["win_streak"][0] = 0

    # find winning and losing streaks
    for i in range(1, stats_df.shape[0]):

        if stats_df["pnl"][i] > 0:
            stats_df["loss_streak"][i] = 0
            stats_df["win_streak"][i] = stats_df["win_streak"][i - 1] + 1

        else:
            stats_df["win_streak"][i] = 0
            stats_df["loss_streak"][i] = stats_df["loss_streak"][i - 1] + 1

    # cumulative PNL
    stats_df["cum_pnl"] = stats_df["pnl"].cumsum()

    # Create Drawdown column
    stats_df["drawdown"] = 0
    for i in range(0, stats_df.shape[0]):

        if i == 0:
            if stats_df["pnl"].iloc[i] > 0:
                stats_df["drawdown"].iloc[i] = 0
            else:
                stats_df["drawdown"].iloc[i] = stats_df["pnl"].iloc[i]
        else:
            if stats_df["pnl"].iloc[i] + stats_df["drawdown"].iloc[i - 1] > 0:
                stats_df["drawdown"].iloc[i] = 0
            else:
                stats_df["drawdown"].iloc[i] = (
                    stats_df["pnl"].iloc[i] + stats_df["drawdown"].iloc[i - 1]
                )

    # create monthly data
    stats_df["month"] = pd.DatetimeIndex(stats_df["trade_date"]).month
    stats_df["year"] = pd.DatetimeIndex(stats_df["trade_date"]).year
    stats_df["month"] = (
        pd.to_datetime(stats_df["month"], format="%m").dt.month_name().str.slice(stop=3)
    )
    stats_df["month_year"] = (
        stats_df["month"] + " " + stats_df["year"].astype(str)
    ).str.slice(stop=11)
    # Dataframe for monthly returns
    stats_df_month = stats_df.groupby(["month_year"], sort=False).sum()
    stats_df_month = stats_df_month.reset_index()

    # Calculate Statistics
    total_days = len(stats_df)
    winning_days = (stats_df["pnl"] > 0).sum()
    losing_days = (stats_df["pnl"] < 0).sum()

    win_ratio = round((winning_days / total_days) * 100, 2)
    max_profit = round(stats_df["pnl"].max(), 2)
    max_loss = round(stats_df["pnl"].min(), 2)
    max_drawdown = round(stats_df["drawdown"].min(), 2)
    max_winning_streak = max(stats_df["win_streak"])
    max_losing_streak = max(stats_df["loss_streak"])
    # avg_profit_on_win_days = stats_df[stats_df["pnl"] > 0]["pnl"].sum() / len(
    #     stats_df[stats_df["pnl"] > 0]
    # )
    # avg_loss_on_loss_days = stats_df[stats_df["pnl"] < 0]["pnl"].sum() / len(
    #     stats_df[stats_df["pnl"] < 0]
    # )
    # avg_profit_per_day = stats_df["pnl"].sum() / len(stats_df)
    # expectancy = round(
    #     (avg_profit_on_win_days * win_ratio + avg_loss_on_loss_days * (100 - win_ratio))
    #     * 0.01,
    #     2,
    # )
    net_profit = round(stats_df["cum_pnl"].iloc[-1], 2)

    KPI = {
        "Total days": total_days,
        "Winning days": winning_days,
        "Losing days": losing_days,
        "Max Profit": max_profit,
        "Max Loss": max_loss,
        "Max Winning Streak": max_winning_streak,
        "Max Losing Streak": max_losing_streak,
        "Max Drawdown": max_drawdown,
        # "Average Profit on win days": avg_profit_on_win_days,
        # "Average Loss on loss days": avg_loss_on_loss_days,
    }
    strategy_stats = pd.DataFrame(KPI.values(), index=KPI.keys(), columns=[" "]).astype(
        int
    )

    # Show Statistics
    st.write("-----")
    col1, col2, col3 = st.columns(3)
    col1.metric(label="Win %", value=str(win_ratio) + " %")
    col2.metric(label="Net Profit (in pts.)", value=str(int(net_profit)))
    # col3.metric(label="Avg. daily profit", value="₹ " + str(int(avg_profit_per_day)))
    st.write("-----")
    st.subheader("Strategy Statistics")
    st.table(strategy_stats)
    st.write("-----")

    # Show equity curve
    st.subheader("Equity Curve")
    fig_pnl = px.line(
        stats_df,
        x="trade_date",
        y="cum_pnl",
        width=800,
        height=500,
    )
    st.plotly_chart(fig_pnl)
    st.write("-----")

    # show drawdown curve
    st.subheader("Drawdown Curve")
    fig_dd = px.line(stats_df, x="trade_date", y="drawdown", width=800, height=500)
    st.plotly_chart(fig_dd)
    st.write("-----")

    # Month-wise PNL
    st.header("Month-wise PNL")
    st.table(
        stats_df_month[["month_year", "pnl"]].style.applymap(
            color_survived, subset=["pnl"]
        )
    )
