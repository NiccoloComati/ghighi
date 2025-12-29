import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import altair as alt
import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:
    gspread = None
    Credentials = None


DATA_COLUMNS = [
    "timestamp_utc",
    "date",
    "player",
    "event",
    "quote",
    "implied_probability",
]


def _today_utc_date_str() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def read(self) -> pd.DataFrame:
        raise NotImplementedError

    def append(self, row: dict) -> None:
        raise NotImplementedError


class LocalCSVStorage(Storage):
    def __init__(self, path: Path) -> None:
        self.path = path
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(columns=DATA_COLUMNS).to_csv(self.path, index=False)

    def read(self) -> pd.DataFrame:
        return pd.read_csv(self.path)

    def append(self, row: dict) -> None:
        df = pd.DataFrame([row], columns=DATA_COLUMNS)
        df.to_csv(self.path, mode="a", header=False, index=False)


class GoogleSheetStorage(Storage):
    def __init__(self, doc_id: str, worksheet: str, credentials: dict) -> None:
        if gspread is None or Credentials is None:
            raise RuntimeError("gspread/google-auth not available")
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(credentials, scopes=scopes)
        client = gspread.authorize(creds)
        self.sheet = client.open_by_key(doc_id).worksheet(worksheet)

    def read(self) -> pd.DataFrame:
        rows = self.sheet.get_all_records()
        if not rows:
            return pd.DataFrame(columns=DATA_COLUMNS)
        return pd.DataFrame(rows)[DATA_COLUMNS]

    def append(self, row: dict) -> None:
        self.sheet.append_row([row[col] for col in DATA_COLUMNS])


def get_storage() -> Storage:
    try:
        has_secrets = "GSHEETS_DOC_ID" in st.secrets
    except Exception:
        has_secrets = False

    if has_secrets:
        credentials_raw = st.secrets.get("GSPREAD_SERVICE_ACCOUNT", "")
        if isinstance(credentials_raw, str):
            credentials = json.loads(credentials_raw)
        else:
            credentials = dict(credentials_raw)
        doc_id = st.secrets["GSHEETS_DOC_ID"]
        worksheet = st.secrets.get("GSHEETS_WORKSHEET", "quotes")
        return GoogleSheetStorage(doc_id, worksheet, credentials)
    return LocalCSVStorage(Path("data/quotes.csv"))


def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in DATA_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[DATA_COLUMNS]


def main() -> None:
    st.set_page_config(page_title="Ghighi Quotes", page_icon="📈", layout="wide")
    st.title("Ghighi Quotes")

    storage = get_storage()
    data = ensure_columns(storage.read())

    events = sorted([e for e in data["event"].dropna().unique() if str(e).strip()])
    players = sorted([p for p in data["player"].dropna().unique() if str(p).strip()])

    st.subheader("Seleziona evento")
    event_options = events + ["+ Aggiungi nuovo evento"]
    event_choice = st.selectbox(
        "Evento",
        event_options if event_options else ["+ Aggiungi nuovo evento"],
    )
    if event_choice == "+ Aggiungi nuovo evento":
        event_name = st.text_input("Nome nuovo evento")
    else:
        event_name = event_choice

    st.divider()

    if event_name:
        st.subheader(f"Quote per: {event_name}")
        event_data = data[data["event"] == event_name].copy()
        event_data["date"] = pd.to_datetime(event_data["date"], errors="coerce")

        chart_col, table_col = st.columns([2, 1], gap="large")

        with chart_col:
            chart_data = event_data.dropna(subset=["player", "date"]).copy()
            chart_data = chart_data.sort_values("date")
            if chart_data.empty:
                st.write("Ancora nessuna quote per questo evento.")
            else:
                max_quote = chart_data["quote"].max()
                y_min = 1.0
                y_max = max_quote * 1.1 if pd.notna(max_quote) else 2.0
                chart = (
                    alt.Chart(chart_data)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("date:T", title="Data"),
                        y=alt.Y(
                            "quote:Q",
                            title="Quota",
                            scale=alt.Scale(domain=[y_min, y_max]),
                        ),
                        color=alt.Color("player:N", title="Giocatore"),
                        tooltip=[
                            alt.Tooltip("player:N", title="Giocatore"),
                            alt.Tooltip("date:T", title="Data", format="%Y-%m-%d"),
                            alt.Tooltip("quote:Q", title="Quota", format=".2f"),
                            alt.Tooltip(
                                "implied_probability:Q",
                                title="Prob. implicita",
                                format=".2%",
                            ),
                        ],
                    )
                )
                st.altair_chart(chart, use_container_width=True)

        with table_col:
            if event_data.empty:
                st.write("Ancora nessuna quote per questo evento.")
            else:
                event_data["timestamp_utc"] = pd.to_datetime(
                    event_data["timestamp_utc"], errors="coerce"
                )
                latest_idx = (
                    event_data.dropna(subset=["player", "timestamp_utc"])
                    .sort_values("timestamp_utc")
                    .groupby("player", as_index=False)
                    .tail(1)
                )
                recent_table = latest_idx[
                    ["date", "player", "quote", "implied_probability"]
                ].sort_values("date", ascending=False)
                recent_table["date"] = recent_table["date"].dt.strftime("%Y-%m-%d")
                recent_table["quote"] = recent_table["quote"].map(lambda x: f"{x:.2f}")
                recent_table["implied_probability"] = recent_table[
                    "implied_probability"
                ].map(lambda x: f"{x:.2%}")
                st.dataframe(recent_table, use_container_width=True, height=360)

        st.divider()

    st.subheader("Aggiungi una quota")
    st.write("La data e fissata automaticamente (UTC).")

    player_options = players + ["+ Aggiungi nuovo giocatore"]
    player_choice = st.selectbox(
        "Giocatore",
        player_options if player_options else ["+ Aggiungi nuovo giocatore"],
    )
    if player_choice == "+ Aggiungi nuovo giocatore":
        player_name = st.text_input("Nome nuovo giocatore")
    else:
        player_name = player_choice

    quote_value = st.number_input(
        "Quota (es. 2.10)",
        min_value=1e-6,
        value=2.10,
        step=0.01,
        format="%.2f",
    )
    quote_value = round(float(quote_value), 2)
    implied_probability = 1 / quote_value if quote_value else 0.0
    st.metric("Probabilita implicita", f"{implied_probability:.2%}")

    submit = st.button("Salva quota", type="primary")
    if submit:
        if not event_name:
            st.error("Scegli o crea un evento.")
            st.stop()
        if not player_name:
            st.error("Scegli o crea un giocatore.")
            st.stop()

        row = {
            "timestamp_utc": _now_utc_iso(),
            "date": _today_utc_date_str(),
            "player": player_name.strip(),
            "event": event_name.strip(),
            "quote": quote_value,
            "implied_probability": round(implied_probability, 6),
        }
        storage.append(row)
        st.success("Quota salvata.")
        st.rerun()


if __name__ == "__main__":
    main()
