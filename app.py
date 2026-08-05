import altair as alt
import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="Eurostat Trade in Services Explorer",
    layout="wide",
)

st.title("Eurostat Trade in Services Explorer")

DATASET = "bop_its6_det"
BASE_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/"
    f"statistics/1.0/data/{DATASET}"
)

REQUEST_TIMEOUT = 60


REPORTERS = {
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
    "Sweden": "SE",
}

REPORTER_OPTIONS = [
    "EU27",
    *sorted(name for name in REPORTERS if name != "EU27"),
]


@st.cache_data(ttl="24h", show_spinner=False)
def get_metadata() -> dict:
    """
    Retrieve a constrained response that contains the dataset's dimensions.

    This still derives metadata from a data response. For a production-scale
    application, Eurostat SDMX codelists would be preferable.
    """
    response = requests.get(
        BASE_URL,
        params={
            "geo": "DK",
            "sinceTimePeriod": "2019",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl="1h", show_spinner=False)
def download_eurostat_data(
    encoded_params: tuple[tuple[str, tuple[str, ...]], ...],
) -> dict:
    """
    Download and cache a Eurostat query.

    Parameters are converted to tuples because cached function arguments
    should be hashable.
    """
    request_params = []

    for dimension, values in encoded_params:
        for value in values:
            request_params.append((dimension, value))

    response = requests.get(
        BASE_URL,
        params=request_params,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def encode_params(
    params: dict[str, str | list[str]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Convert a parameter dictionary into a stable, hashable representation."""
    encoded = []

    for key, value in sorted(params.items()):
        if isinstance(value, list):
            values = tuple(str(item) for item in value)
        else:
            values = (str(value),)

        encoded.append((key, values))

    return tuple(encoded)


def get_options(data: dict, dimension: str) -> dict[str, str]:
    """Return display label -> Eurostat code mappings."""
    category = data["dimension"][dimension]["category"]
    labels = category.get("label", {})
    index = category.get("index", {})

    if isinstance(index, dict):
        ordered_codes = [
            code
            for code, _position in sorted(
                index.items(),
                key=lambda item: item[1],
            )
        ]
    else:
        # Defensive fallback for JSON-stat responses using an ordered list.
        ordered_codes = list(index)

    return {
        f"{labels.get(code, code)} ({code})": code
        for code in ordered_codes
    }


def find_option(
    options: dict[str, str],
    preferred_codes: tuple[str, ...],
    preferred_text: tuple[str, ...] = (),
) -> str:
    """Find the most appropriate default display label."""
    for label, code in options.items():
        if code in preferred_codes:
            return label

    for label in options:
        upper_label = label.upper()
        if any(text in upper_label for text in preferred_text):
            return label

    return next(iter(options))


def get_default_selection(
    dimension: str,
    options: dict[str, str],
) -> list[str]:
    if not options:
        return []

    if dimension == "partner":
        return [
            find_option(
                options,
                preferred_codes=(
                    "EXT_EU27_2020",
                    "EXT_EU27",
                    "EXT",
                ),
                preferred_text=(
                    "EXTRA-EU",
                    "EXTRA EU",
                ),
            )
        ]

    if dimension == "stk_flow":
        return [
            find_option(
                options,
                preferred_codes=("EXP", "CRE", "X"),
                preferred_text=("EXPORT", "CREDIT"),
            )
        ]

    if dimension == "bop_item":
        return [
            find_option(
                options,
                preferred_codes=("S", "SERV", "TOTAL"),
                preferred_text=("SERVICES",),
            )
        ]

    if dimension == "unit":
        return [
            find_option(
                options,
                preferred_codes=("MIO_EUR",),
                preferred_text=("MILLION EURO",),
            )
        ]

    return [next(iter(options))]


def invert_category_index(category: dict) -> dict[int, str]:
    """Return position -> category code mapping."""
    index = category.get("index", {})

    if isinstance(index, dict):
        return {
            position: code
            for code, position in index.items()
        }

    return {
        position: code
        for position, code in enumerate(index)
    }


def decode_eurostat_response(data: dict) -> pd.DataFrame:
    """Decode Eurostat's flattened JSON-stat observation structure."""
    dimensions = data["id"]
    sizes = data["size"]

    category_maps = {}

    for dimension in dimensions:
        category = data["dimension"][dimension]["category"]
        position_to_code = invert_category_index(category)
        labels = category.get("label", {})

        category_maps[dimension] = {
            position: (
                code,
                labels.get(code, code),
            )
            for position, code in position_to_code.items()
        }

    status_values = data.get("status", {})
    rows = []

    for observation_key, value in data.get("value", {}).items():
        observation_index = int(observation_key)
        remainder = observation_index
        coordinates = {}

        # JSON-stat uses row-major order: the final dimension varies fastest.
        for dimension, size in reversed(list(zip(dimensions, sizes))):
            coordinates[dimension] = remainder % size
            remainder //= size

        row = {
            "value": value,
            "status": status_values.get(
                observation_key,
                status_values.get(str(observation_index)),
            ),
        }

        for dimension in dimensions:
            position = coordinates[dimension]
            code, label = category_maps[dimension][position]

            row[dimension] = code
            row[f"{dimension}_label"] = label

        rows.append(row)

    return pd.DataFrame(rows)


def prepare_display_df(df: pd.DataFrame) -> pd.DataFrame:
    display_df = df.copy()

    rename_map = {
        "geo_label": "Reporter",
        "time": "Year",
        "partner_label": "Partner",
        "bop_item_label": "Service item",
        "stk_flow_label": "Flow",
        "unit_label": "Unit",
        "value": "Value",
        "status": "Status",
    }

    desired_columns = [
        "geo_label",
        "partner_label",
        "bop_item_label",
        "stk_flow_label",
        "unit_label",
        "time",
        "value",
        "status",
    ]

    existing_columns = [
        column
        for column in desired_columns
        if column in display_df.columns
    ]

    display_df = display_df[existing_columns].rename(columns=rename_map)

    if "Year" in display_df.columns:
        display_df["Year"] = display_df["Year"].astype(str)

    if "Value" in display_df.columns:
        display_df["Value"] = pd.to_numeric(
            display_df["Value"],
            errors="coerce",
        )

    if "Status" in display_df.columns and display_df["Status"].isna().all():
        display_df = display_df.drop(columns="Status")

    return display_df


def make_trend_chart(display_df: pd.DataFrame) -> alt.Chart:
    trend_df = display_df.copy()

    component_dimensions = []

    if (
        "Service item" in trend_df.columns
        and trend_df["Service item"].nunique() > 1
    ):
        component_dimensions.append("Service item")

    if component_dimensions:
        trend_df["Component"] = (
            trend_df[component_dimensions]
            .fillna("")
            .astype(str)
            .agg(" | ".join, axis=1)
        )
    else:
        trend_df["Component"] = "Total"

    group_columns = ["Year", "Partner", "Component"]

    # Flow and unit are single selections, but retaining them in tooltips
    # makes the chart easier to interpret.
    for optional_column in ("Flow", "Unit"):
        if optional_column in trend_df.columns:
            group_columns.append(optional_column)

    trend_df = (
        trend_df
        .groupby(group_columns, as_index=False, dropna=False)["Value"]
        .sum()
    )

    tooltip = [
        alt.Tooltip("Year:N", title="Year"),
        alt.Tooltip("Partner:N", title="Partner"),
        alt.Tooltip("Component:N", title="Component"),
    ]

    if "Flow" in trend_df.columns:
        tooltip.append(alt.Tooltip("Flow:N", title="Flow"))

    if "Unit" in trend_df.columns:
        tooltip.append(alt.Tooltip("Unit:N", title="Unit"))

    tooltip.append(
        alt.Tooltip("Value:Q", title="Value", format=",.1f")
    )

    base_chart = (
        alt.Chart(trend_df)
        .mark_bar()
        .encode(
            x=alt.X(
                "Year:N",
                title="Year",
                sort=sorted(trend_df["Year"].unique()),
            ),
            xOffset=alt.XOffset(
                "Partner:N",
                title="Partner",
            ),
            y=alt.Y(
                "Value:Q",
                title="Trade value",
                stack="zero",
            ),
            color=alt.Color(
                "Component:N",
                title="Service item",
            ),
            tooltip=tooltip,
        )
    )

    if trend_df["Partner"].nunique() <= 1:
        return base_chart.properties(height=500)

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
            fontSize=11,
        )
        .encode(
            x=alt.X(
                "Year:N",
                sort=sorted(label_df["Year"].unique()),
            ),
            xOffset=alt.XOffset("Partner:N"),
            y=alt.Y("Value:Q", stack=None),
            text=alt.Text("Partner:N"),
        )
    )

    return (base_chart + label_chart).properties(height=500)


try:
    metadata = get_metadata()
except requests.RequestException as error:
    st.error(f"Could not retrieve Eurostat metadata: {error}")
    st.stop()
except (KeyError, TypeError, ValueError) as error:
    st.error(f"Unexpected Eurostat metadata structure: {error}")
    st.stop()


with st.sidebar:
    st.header("Filters")

    reporter_name = st.selectbox(
        "Reporter",
        REPORTER_OPTIONS,
        index=0,
    )
    reporter_code = REPORTERS[reporter_name]

    params: dict[str, str | list[str]] = {
        "geo": reporter_code,
    }

    missing_selections = []

    ignored_filter_dimensions = {
        "geo",
        "time",
        "freq",
    }

    for dimension in metadata["id"]:
        if dimension in ignored_filter_dimensions:
            continue

        options = get_options(metadata, dimension)

        if not options:
            continue

        defaults = get_default_selection(dimension, options)

        # Flows and units must be single selections because they cannot
        # safely be summed in one chart.
        if dimension in {"stk_flow", "unit"}:
            default_label = defaults[0]

            selected_label = st.selectbox(
                dimension.replace("_", " ").title(),
                options=list(options.keys()),
                index=list(options.keys()).index(default_label),
            )

            params[dimension] = options[selected_label]

        else:
            selected_labels = st.multiselect(
                dimension.replace("_", " ").title(),
                options=list(options.keys()),
                default=defaults,
                max_selections=5 if dimension == "partner" else None,
            )

            if selected_labels:
                params[dimension] = [
                    options[label]
                    for label in selected_labels
                ]
            else:
                missing_selections.append(dimension)

    time_category = metadata["dimension"]["time"]["category"]
    time_index = time_category.get("index", {})

    if isinstance(time_index, dict):
        time_codes = time_index.keys()
    else:
        time_codes = time_index

    available_years = sorted(
        int(year)
        for year in time_codes
        if str(year).isdigit()
    )

    if not available_years:
        st.error("No annual time periods were found in the metadata.")
        st.stop()

    latest_year = max(available_years)
    earliest_default_year = max(
        min(available_years),
        latest_year - 5,
    )

    year_range = st.slider(
        "Year range",
        min_value=min(available_years),
        max_value=latest_year,
        value=(earliest_default_year, latest_year),
    )

    params["time"] = [
        str(year)
        for year in available_years
        if year_range[0] <= year <= year_range[1]
    ]

    download_disabled = bool(missing_selections)

    download_clicked = st.button(
        "Download data",
        type="primary",
        disabled=download_disabled,
    )

    if missing_selections:
        readable_dimensions = ", ".join(
            dimension.replace("_", " ")
            for dimension in missing_selections
        )
        st.warning(
            f"Select at least one value for: {readable_dimensions}."
        )


st.write(
    f"Selected reporter: **{reporter_name} ({reporter_code})**"
)


if download_clicked:
    try:
        with st.spinner("Downloading from Eurostat..."):
            data = download_eurostat_data(
                encode_params(params)
            )

        if not data.get("value"):
            st.warning("No observations were returned for this selection.")
            st.session_state.pop("eurostat_display_df", None)
        else:
            raw_df = decode_eurostat_response(data)
            display_df = prepare_display_df(raw_df)

            st.session_state["eurostat_display_df"] = display_df
            st.session_state["eurostat_reporter_code"] = reporter_code

    except requests.RequestException as error:
        st.error(f"Eurostat request failed: {error}")
    except (KeyError, TypeError, ValueError) as error:
        st.error(f"Could not process the Eurostat response: {error}")


if "eurostat_display_df" in st.session_state:
    display_df = st.session_state["eurostat_display_df"]
    saved_reporter_code = st.session_state.get(
        "eurostat_reporter_code",
        reporter_code,
    )

    st.success("Data available")

    st.subheader("Overview")

    metric_col1, metric_col2 = st.columns(2)

    with metric_col1:
        st.metric(
            "Observations",
            f"{len(display_df):,}",
        )

    with metric_col2:
        year_count = (
            display_df["Year"].nunique()
            if "Year" in display_df.columns
            else 0
        )
        st.metric("Years", year_count)

    required_chart_columns = {
        "Year",
        "Partner",
        "Value",
    }

    if required_chart_columns.issubset(display_df.columns):
        st.subheader("Trend over time")
        st.caption(
            "Partners are shown side by side. Multiple service items "
            "are stacked within each partner bar."
        )

        chart = make_trend_chart(display_df)

        st.altair_chart(
            chart,
            use_container_width=True,
        )

    st.subheader("Selected data")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = display_df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        "Download selected data as CSV",
        data=csv_bytes,
        file_name=f"{saved_reporter_code}_{DATASET}.csv",
        mime="text/csv",
        on_click="ignore",
    )

else:
    st.info(
        "Choose filters in the sidebar, then click Download data."
    )