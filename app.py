import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
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
    st.caption("Log personal quotes for events and track implied probabilities over time.")

    storage = get_storage()
    data = ensure_columns(storage.read())

    events = sorted([e for e in data["event"].dropna().unique() if str(e).strip()])
    players = sorted([p for p in data["player"].dropna().unique() if str(p).strip()])

    st.subheader("Select event")
    event_options = events + ["+ Add new event"]
    event_choice = st.selectbox("Event", event_options if event_options else ["+ Add new event"])
    if event_choice == "+ Add new event":
        event_name = st.text_input("New event name")
    else:
        event_name = event_choice

    st.divider()

    if event_name:
        st.subheader(f"Quotes for: {event_name}")
        event_data = data[data["event"] == event_name].copy()
        event_data["date"] = pd.to_datetime(event_data["date"], errors="coerce")

        player_date_counts = (
            event_data.dropna(subset=["player", "date"])
            .groupby("player")["date"]
            .nunique()
        )
        players_with_series = player_date_counts[player_date_counts >= 2].index.tolist()

        if not players_with_series:
            st.info(
                "Plot will be displayed when more than 2 quotes are input on different days for at least one player."
            )
            if not event_data.empty:
                display_table = (
                    event_data[["player", "date", "quote", "implied_probability"]]
                    .sort_values(["player", "date"], ascending=[True, True])
                )
                st.dataframe(display_table, use_container_width=True)
        else:
            chart_data = event_data[event_data["player"].isin(players_with_series)].copy()
            chart_data = chart_data.sort_values("date")
            pivot = chart_data.pivot_table(
                index="date",
                columns="player",
                values="quote",
                aggfunc="last",
            )
            st.line_chart(pivot, use_container_width=True)

        st.divider()

    st.subheader("Add a quote")
    st.write("Date is fixed automatically (UTC).")

    player_options = players + ["+ Add new player"]
    player_choice = st.selectbox("Player", player_options if player_options else ["+ Add new player"])
    if player_choice == "+ Add new player":
        player_name = st.text_input("New player name")
    else:
        player_name = player_choice

    quote_value = st.number_input("Quote (e.g. 2.1)", min_value=1e-6, value=2.1, step=0.1, format="%.4f")
    implied_probability = 1 / quote_value if quote_value else 0.0
    st.metric("Implied probability", f"{implied_probability:.2%}")

    submit = st.button("Save quote", type="primary")
    if submit:
        if not event_name:
            st.error("Please choose or create an event.")
            st.stop()
        if not player_name:
            st.error("Please choose or create a player.")
            st.stop()

        row = {
            "timestamp_utc": _now_utc_iso(),
            "date": _today_utc_date_str(),
            "player": player_name.strip(),
            "event": event_name.strip(),
            "quote": float(quote_value),
            "implied_probability": implied_probability,
        }
        storage.append(row)
        st.success("Quote saved.")
        st.rerun()


if __name__ == "__main__":
    main()
