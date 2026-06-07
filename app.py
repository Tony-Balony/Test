import streamlit as st
import pandas as pd
import requests
import altair as alt

st.set_page_config(page_title="Eurostat Trade in Services Explorer", layout="wide")

st.title("Eurostat Trade in Services Explorer")

DATASET = "bop_its6_det"
BASE_URL = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{DATASET}"

reporters = {
    "EU27": "EU27_2020",
    "Austria": "AT",
    "Belgium": "BE",
    "Bulgaria": "BG",
    "Croatia": "HR",
    "Cyprus": "CY",
    "Czechia": "CZ",
    "Denmark": "DK",
    "Estonia": "EE",
    "Finland": "FI",
    "France": "FR",
    "Germany": "DE",
    "Greece": "EL",
    "Hungary": "HU",
    "Ireland": "IE",
    "Italy": "IT",
    "Latvia": "LV",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Malta": "MT",
    "Netherlands": "NL",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE"
}

reporter_options = ["EU27"] + sorted([x for x in reporters if x != "EU27"])


@st.cache_data
def get_metadata():
    r = requests.get(BASE_URL, params={"geo": "DK"})
    r.raise_for_status()
    return r.json()


def get_options(data, dim):
    cats = data["dimension"][dim]["category"]
    labels = cats.get("label", {})
    index = cats.get("index", {})
    ordered = sorted(index.items(), key=lambda x: x[1])

    return {
        f"{labels.get(code, code)} ({code})": code
        for code, _ in ordered
    }


def get_default_selection(dim, options):
    default_selection = list(options.keys())[:1]

    if dim == "partner":
        for label, code in options.items():
            if code in ["EXT_EU27_2020", "EXT_EU27", "EXT"]:
                return [label]

        extra_eu = [
            label for label in options
            if "EXTRA" in label.upper()
            or "EXTRA-EU" in label.upper()
            or "EXTRA EU" in label.upper()
        ]

        if extra_eu:
            return [extra_eu[0]]

    if dim == "flow":
        for label, code in options.items():
            if code in ["EXP", "X", "C"]:
                return [label]

        exports = [
            label for label in options
            if "EXPORT" in label.upper()
            or "CREDIT" in label.upper()
        ]

        if exports:
            return [exports[0]]

    if dim == "bop_item":
        for label, code in options.items():
            if code in ["S", "SERV", "TOTAL"]:
                return [label]

        total_services = [
            label for label in options
            if "TOTAL SERVICES" in label.upper()
            or "SERVICES" == label.upper().split(" (")[0]
        ]

        if total_services:
            return [total_services[0]]

    return default_selection


def decode_eurostat_response(data):
    dimensions = data["id"]
    sizes = data["size"]
    rows = []

    for obs_index, value in data["value"].items():
        obs_index = int(obs_index)
        coords = {}
        remainder = obs_index

        for dim, size in reversed(list(zip(dimensions, sizes))):
            coords[dim] = remainder % size
            remainder = remainder // size

        row = {"value": value}

        for dim in dimensions:
            dim_index = coords[dim]
            cats = data["dimension"][dim]["category"]

            code = next(
                k for k, v in cats["index"].items()
                if v == dim_index
            )

            label = cats.get("label", {}).get(code, code)

            row[dim] = code
            row[f"{dim}_label"] = label

        rows.append(row)

    return pd.DataFrame(rows)


def prepare_display_df(df):
    display_df = df.copy()

    ignore_columns = [
        "freq",
        "freq_label",
        "time_label",
        "currency",
        "currency_label"
    ]

    display_df = display_df.drop(
        columns=[col for col in ignore_columns if col in display_df.columns],
        errors="ignore"
    )

    label_columns = [
        col for col in display_df.columns
        if col.endswith("_label") and col not in ignore_columns
    ]

    columns_to_keep = label_columns + ["time", "value"]
    columns_to_keep = [col for col in columns_to_keep if col in display_df.columns]

    display_df = display_df[columns_to_keep]

    display_df = display_df.rename(
        columns={
            "geo_label": "Reporter",
            "time": "Year",
            "partner_label": "Partner",
            "bop_item_label": "Service item",
            "flow_label": "Flow",
            "unit_label": "Unit",
            "value": "Value"
        }
    )

    display_df = display_df.loc[:, ~display_df.columns.duplicated()]

    if "Year" in display_df.columns:
        display_df["Year"] = display_df["Year"].astype(str)

    if "Value" in display_df.columns:
        display_df["Value"] = pd.to_numeric(display_df["Value"], errors="coerce")

    return display_df


metadata = get_metadata()

with st.sidebar:
    st.header("Filters")

    reporter_name = st.selectbox(
        "Reporter",
        reporter_options,
        index=0
    )

    reporter_code = reporters[reporter_name]

    params = {"geo": reporter_code}

    ignored_filter_dims = [
        "geo",
        "time",
        "freq",
        "currency"
    ]

    for dim in metadata["id"]:
        if dim in ignored_filter_dims:
            continue

        options = get_options(metadata, dim)
        default_selection = get_default_selection(dim, options)

        if dim == "partner":
            selected = st.multiselect(
                dim,
                list(options.keys()),
                default=default_selection,
                max_selections=5
            )
        else:
            selected = st.multiselect(
                dim,
                list(options.keys()),
                default=default_selection
            )

        if selected:
            params[dim] = [options[x] for x in selected]

    available_years = sorted(
        [
            int(year)
            for year in metadata["dimension"]["time"]["category"]["index"].keys()
            if str(year).isdigit()
        ]
    )

    latest_year = max(available_years)
    start_year = max(min(available_years), latest_year - 5)

    year_range = st.slider(
        "Year range",
        min_value=min(available_years),
        max_value=latest_year,
        value=(start_year, latest_year)
    )

    params["time"] = [
        str(year)
        for year in available_years
        if year_range[0] <= year <= year_range[1]
    ]

    download_clicked = st.button("Download Data", type="primary")


st.write(f"Selected reporter: **{reporter_name} ({reporter_code})**")

if download_clicked:

    with st.spinner("Downloading from Eurostat..."):
        response = requests.get(BASE_URL, params=params)

    if response.status_code != 200:
        st.error(f"HTTP Error {response.status_code}")
        st.stop()

    data = response.json()

    if "value" not in data:
        st.warning("No observations returned.")
        st.stop()

    df = decode_eurostat_response(data)
    display_df = prepare_display_df(df)

    st.success("Download complete")

    st.subheader("Overview")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Observations", f"{len(display_df):,}")

    with col2:
        st.metric("Years", display_df["Year"].nunique())

    if (
        "Year" in display_df.columns
        and "Partner" in display_df.columns
        and "Value" in display_df.columns
    ):
        st.subheader("Trend over time.  Hover over the bars to see details. Note that all selections stack.")
                    
                     

        trend_df = display_df.copy()

        component_dimensions = []

        if (
            "Service item" in trend_df.columns
            and trend_df["Service item"].nunique() > 1
        ):
            component_dimensions.append("Service item")

        if (
            "Flow" in trend_df.columns
            and trend_df["Flow"].nunique() > 1
        ):
            component_dimensions.append("Flow")

        if component_dimensions:
            trend_df["Component"] = (
                trend_df[component_dimensions]
                .astype(str)
                .agg(" | ".join, axis=1)
            )
        else:
            trend_df["Component"] = "Total"

        trend_df = (
            trend_df
            .groupby(["Year", "Partner", "Component"], as_index=False)["Value"]
            .sum()
        )

        base_chart = (
            alt.Chart(trend_df)
            .mark_bar()
            .encode(
                x=alt.X("Year:N", title="Year"),
                xOffset=alt.XOffset("Partner:N"),
                y=alt.Y("Value:Q", title="Trade value", stack="zero"),
                color=alt.Color("Component:N", title="Component"),
                tooltip=[
                    alt.Tooltip("Year:N", title="Year"),
                    alt.Tooltip("Partner:N", title="Partner"),
                    alt.Tooltip("Component:N", title="Component"),
                    alt.Tooltip("Value:Q", title="Value", format=",.0f")
                ]
            )
        )

        if trend_df["Partner"].nunique() > 1:
            label_df = (
                trend_df
                .groupby(["Year", "Partner"], as_index=False)["Value"]
                .sum()
            )

            label_chart = (
                alt.Chart(label_df)
                .mark_text(
                    align="center",
                    baseline="bottom",
                    dy=-4,
                    fontSize=11
                )
                .encode(
                    x=alt.X("Year:N", title="Year"),
                    xOffset=alt.XOffset("Partner:N"),
                    y=alt.Y("Value:Q", stack=None),
                    text=alt.Text("Partner:N")
                )
            )

            trend_chart = (base_chart + label_chart).properties(height=500)
        else:
            trend_chart = base_chart.properties(height=500)

        st.altair_chart(trend_chart, use_container_width=True)

    st.subheader("Selected data")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    csv = display_df.to_csv(index=False)

    st.download_button(
        "Download selected data as CSV",
        csv,
        f"{reporter_code}_{DATASET}.csv",
        "text/csv"
    )

else:
    st.info("Choose filters in the sidebar, then click Download Data.")