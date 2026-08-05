import streamlit as st
import pandas as pd
import requests
import altair as alt


# ------------------------------------------------------------
# PAGE CONFIGURATION
# ------------------------------------------------------------

st.set_page_config(
    page_title="Eurostat Cross-Border Trade in Services Explorer",
    layout="wide"
)

st.title("Eurostat Trade in Services Explorer")


# ------------------------------------------------------------
# EUROSTAT DATASET
# ------------------------------------------------------------

DATASET = "bop_its6_det"

BASE_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/"
    f"statistics/1.0/data/{DATASET}"
)


# ------------------------------------------------------------
# REPORTERS
# ------------------------------------------------------------

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

reporter_options = (
    ["EU27"]
    + sorted(
        reporter
        for reporter in reporters
        if reporter != "EU27"
    )
)


# ------------------------------------------------------------
# PARTNER FILTERING
# ------------------------------------------------------------

EU_MEMBER_CODES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
    "DE", "EL", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT",
    "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"
}

EU_RELATED_CODE_PARTS = [
    "EU",
    "EA",
    "EMU",
    "INTRA",
    "INT_EU",
    "EU27",
    "EU28",
    "EU27_2020",
    "EU28_2020",
    "EA19",
    "EA20",
    "ROW",
    "WORLD_REST",
    "IMF"
]

EU_RELATED_LABEL_PARTS = [
    "EUROPEAN UNION",
    "EUROPEAN",
    "EURO AREA",
    "EURO",
    "EU27",
    "EU-27",
    "EU28",
    "EU-28",
    "EUROZONE",
    "INTRA-EU",
    "INTRA EU",
    "MEMBER STATES",
    "EU INSTITUTIONS",
    "REST OF WORLD",
    "CANDIDATE COUNTRIES",
    "IMF"
]


def is_extra_eu_partner(code, label):
    """
    Identify Extra-EU aggregates.

    Extra-EU aggregates are retained even though their labels
    contain EU-related wording.
    """

    code_upper = str(code).upper()
    label_upper = str(label).upper()

    return (
        "EXTRA" in code_upper
        or "EXT_EU" in code_upper
        or "EXTRA-EU" in label_upper
        or "EXTRA EU" in label_upper
    )


def is_eu_related_partner(code, label):
    """
    Return True when a partner should be excluded from the partner list.
    """

    code_upper = str(code).upper()
    label_upper = str(label).upper()

    # Retain Extra-EU27 aggregates
    if is_extra_eu_partner(code, label):
        return False

    # Exclude individual EU Member States
    if code_upper in EU_MEMBER_CODES:
        return True

    # Exclude EU-related aggregate codes
    if any(
        code_part in code_upper
        for code_part in EU_RELATED_CODE_PARTS
    ):
        return True

    # Exclude EU-related labels
    if any(
        label_part in label_upper
        for label_part in EU_RELATED_LABEL_PARTS
    ):
        return True

    return False


# ------------------------------------------------------------
# EUROSTAT METADATA
# ------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def get_metadata():
    """
    Download dataset metadata.
    """

    response = requests.get(
        BASE_URL,
        params={"geo": "DK"},
        timeout=60
    )

    response.raise_for_status()

    return response.json()


def get_options(data, dimension):
    """
    Build a dictionary of display labels and Eurostat codes
    for a dimension.
    """

    categories = data["dimension"][dimension]["category"]

    labels = categories.get("label", {})
    category_index = categories.get("index", {})

    ordered_categories = sorted(
        category_index.items(),
        key=lambda item: item[1]
    )

    options = {}

    for code, _ in ordered_categories:

        label = labels.get(code, code)

        if (
            dimension == "partner"
            and is_eu_related_partner(code, label)
        ):
            continue

        display_label = f"{label} ({code})"
        options[display_label] = code

    return options


def get_default_selection(dimension, options):
    """
    Choose a sensible default for each filter.

    All filters use multiselect, including STK_FLOW.
    """

    if not options:
        return []

    default_selection = [next(iter(options))]

    # --------------------------------------------------------
    # Partner
    # --------------------------------------------------------

    if dimension == "partner":

        # Prefer Extra-EU27
        for display_label, code in options.items():
            if is_extra_eu_partner(code, display_label):
                return [display_label]

        preferred_partner_codes = [
            "US",
            "USA",
            "GB",
            "UK",
            "CN",
            "CH",
            "JP"
        ]

        for preferred_code in preferred_partner_codes:
            for display_label, code in options.items():
                if code == preferred_code:
                    return [display_label]

        preferred_partner_labels = [
            "UNITED STATES",
            "UNITED KINGDOM",
            "CHINA",
            "SWITZERLAND",
            "JAPAN"
        ]

        for preferred_label in preferred_partner_labels:
            for display_label in options:
                if preferred_label in display_label.upper():
                    return [display_label]

    # --------------------------------------------------------
    # Stock flow
    # --------------------------------------------------------

    if dimension == "stk_flow":

        preferred_flow_codes = [
            "CRE",
            "EXP",
            "X",
            "C"
        ]

        for preferred_code in preferred_flow_codes:
            for display_label, code in options.items():
                if code == preferred_code:
                    return [display_label]

        exports_or_credit = [
            display_label
            for display_label in options
            if (
                "EXPORT" in display_label.upper()
                or "CREDIT" in display_label.upper()
            )
        ]

        if exports_or_credit:
            return [exports_or_credit[0]]

    # --------------------------------------------------------
    # Service item
    # --------------------------------------------------------

    if dimension == "bop_item":

        preferred_service_codes = [
            "S",
            "SERV",
            "TOTAL"
        ]

        for preferred_code in preferred_service_codes:
            for display_label, code in options.items():
                if code == preferred_code:
                    return [display_label]

        total_services = [
            display_label
            for display_label in options
            if (
                "TOTAL SERVICES" in display_label.upper()
                or (
                    display_label
                    .upper()
                    .split(" (")[0]
                    .strip()
                    == "SERVICES"
                )
            )
        ]

        if total_services:
            return [total_services[0]]

    return default_selection


# ------------------------------------------------------------
# EUROSTAT RESPONSE DECODING
# ------------------------------------------------------------

def decode_eurostat_response(data):
    """
    Convert a Eurostat JSON-stat response to a pandas DataFrame.
    """

    dimensions = data["id"]
    dimension_sizes = data["size"]

    observations = data.get("value", {})
    rows = []

    reverse_category_maps = {}

    for dimension in dimensions:

        category_index = (
            data["dimension"][dimension]["category"]["index"]
        )

        reverse_category_maps[dimension] = {
            position: code
            for code, position in category_index.items()
        }

    for observation_index, value in observations.items():

        observation_index = int(observation_index)

        coordinates = {}
        remainder = observation_index

        for dimension, size in reversed(
            list(zip(dimensions, dimension_sizes))
        ):
            coordinates[dimension] = remainder % size
            remainder //= size

        row = {
            "value": value
        }

        for dimension in dimensions:

            dimension_position = coordinates[dimension]

            category = (
                data["dimension"][dimension]["category"]
            )

            code = reverse_category_maps[dimension].get(
                dimension_position
            )

            label = category.get("label", {}).get(
                code,
                code
            )

            row[dimension] = code
            row[f"{dimension}_label"] = label

        rows.append(row)

    return pd.DataFrame(rows)


def prepare_display_df(df):
    """
    Create a readable table for display and CSV download.
    """

    display_df = df.copy()

    ignore_columns = [
        "freq",
        "freq_label",
        "time_label",
        "currency",
        "currency_label"
    ]

    display_df = display_df.drop(
        columns=[
            column
            for column in ignore_columns
            if column in display_df.columns
        ],
        errors="ignore"
    )

    label_columns = [
        column
        for column in display_df.columns
        if (
            column.endswith("_label")
            and column not in ignore_columns
        )
    ]

    columns_to_keep = label_columns + [
        "time",
        "value"
    ]

    columns_to_keep = [
        column
        for column in columns_to_keep
        if column in display_df.columns
    ]

    display_df = display_df[columns_to_keep]

    display_df = display_df.rename(
        columns={
            "geo_label": "Reporter",
            "time": "Year",
            "partner_label": "Partner",
            "bop_item_label": "Service item",
            "stk_flow_label": "Flow",
            "flow_label": "Flow",
            "unit_label": "Unit",
            "value": "Value"
        }
    )

    display_df = display_df.loc[
        :,
        ~display_df.columns.duplicated()
    ]

    if "Year" in display_df.columns:
        display_df["Year"] = (
            display_df["Year"]
            .astype(str)
        )

    if "Value" in display_df.columns:
        display_df["Value"] = pd.to_numeric(
            display_df["Value"],
            errors="coerce"
        )

    preferred_column_order = [
        "Reporter",
        "Partner",
        "Service item",
        "Flow",
        "Unit",
        "Year",
        "Value"
    ]

    ordered_columns = [
        column
        for column in preferred_column_order
        if column in display_df.columns
    ]

    remaining_columns = [
        column
        for column in display_df.columns
        if column not in ordered_columns
    ]

    display_df = display_df[
        ordered_columns + remaining_columns
    ]

    return display_df


def get_flow_sort_value(flow):
    """
    Assign a stable order to the main Eurostat flow labels.
    """

    flow_upper = str(flow).upper()

    if "CREDIT" in flow_upper or "EXPORT" in flow_upper:
        return 1

    if "DEBIT" in flow_upper or "IMPORT" in flow_upper:
        return 2

    if "BALANCE" in flow_upper:
        return 3

    return 99


# ------------------------------------------------------------
# METADATA LOADING
# ------------------------------------------------------------

try:
    metadata = get_metadata()

except requests.exceptions.RequestException as error:
    st.error(
        "Could not connect to the Eurostat API. "
        f"Details: {error}"
    )
    st.stop()

except (KeyError, ValueError) as error:
    st.error(
        "Eurostat returned an unexpected metadata response. "
        f"Details: {error}"
    )
    st.stop()


# ------------------------------------------------------------
# SIDEBAR FILTERS
# ------------------------------------------------------------

with st.sidebar:

    st.header("Filters")

    reporter_name = st.selectbox(
        "Reporter",
        reporter_options,
        index=0
    )

    reporter_code = reporters[reporter_name]

    params = {
        "geo": reporter_code
    }

    ignored_filter_dimensions = [
        "geo",
        "time",
        "freq",
        "currency"
    ]

    filter_titles = {
        "partner": "Partner",
        "bop_item": "Service item",
        "stk_flow": "Flow",
        "unit": "Unit"
    }

    for dimension in metadata["id"]:

        if dimension in ignored_filter_dimensions:
            continue

        options = get_options(
            metadata,
            dimension
        )

        if not options:
            continue

        default_selection = get_default_selection(
            dimension,
            options
        )

        selected = st.multiselect(
            label=filter_titles.get(
                dimension,
                dimension.replace("_", " ").title()
            ),
            options=list(options.keys()),
            default=default_selection,
            key=f"filter_{dimension}"
        )

        if selected:
            params[dimension] = [
                options[selected_option]
                for selected_option in selected
            ]

    # --------------------------------------------------------
    # Years
    # --------------------------------------------------------

    available_years = sorted(
        int(year)
        for year in (
            metadata["dimension"]["time"]["category"]["index"]
            .keys()
        )
        if str(year).isdigit()
    )

    if not available_years:
        st.error(
            "No years were found in the Eurostat metadata."
        )
        st.stop()

    earliest_year = min(available_years)
    latest_year = max(available_years)

    default_start_year = max(
        earliest_year,
        latest_year - 5
    )

    year_range = st.slider(
        "Year range",
        min_value=earliest_year,
        max_value=latest_year,
        value=(default_start_year, latest_year)
    )

    params["time"] = [
        str(year)
        for year in available_years
        if year_range[0] <= year <= year_range[1]
    ]

    download_clicked = st.button(
        "Download Data",
        type="primary",
        use_container_width=True
    )


# ------------------------------------------------------------
# MAIN PAGE
# ------------------------------------------------------------

st.write(
    f"Selected reporter: "
    f"**{reporter_name} ({reporter_code})**"
)


if download_clicked:

    try:

        with st.spinner("Downloading from Eurostat..."):

            response = requests.get(
                BASE_URL,
                params=params,
                timeout=120
            )

            response.raise_for_status()

            data = response.json()

    except requests.exceptions.Timeout:

        st.error(
            "The Eurostat request timed out. Try selecting fewer "
            "partners, service items, flows or years."
        )
        st.stop()

    except requests.exceptions.HTTPError:

        st.error(
            f"Eurostat returned HTTP error "
            f"{response.status_code}."
        )

        try:
            st.code(response.text[:2000])
        except Exception:
            pass

        st.stop()

    except requests.exceptions.RequestException as error:

        st.error(
            "A connection error occurred while contacting Eurostat. "
            f"Details: {error}"
        )
        st.stop()

    except ValueError:

        st.error(
            "Eurostat did not return a valid JSON response."
        )
        st.stop()

    if "value" not in data or not data["value"]:

        st.warning(
            "No observations were returned for the selected filters."
        )
        st.stop()

    try:

        df = decode_eurostat_response(data)
        display_df = prepare_display_df(df)

    except (KeyError, ValueError, TypeError) as error:

        st.error(
            "The Eurostat response could not be decoded. "
            f"Details: {error}"
        )
        st.stop()

    if display_df.empty:

        st.warning(
            "The selected filters returned no usable observations."
        )
        st.stop()

    st.success("Download complete")

    # --------------------------------------------------------
    # OVERVIEW
    # --------------------------------------------------------

    st.subheader("Overview")

    metric_columns = st.columns(3)

    with metric_columns[0]:

        st.metric(
            "Observations",
            f"{len(display_df):,}"
        )

    with metric_columns[1]:

        number_of_years = (
            display_df["Year"].nunique()
            if "Year" in display_df.columns
            else 0
        )

        st.metric(
            "Years",
            number_of_years
        )

    with metric_columns[2]:

        number_of_flows = (
            display_df["Flow"].nunique()
            if "Flow" in display_df.columns
            else 0
        )

        st.metric(
            "Flows",
            number_of_flows
        )

    # --------------------------------------------------------
    # TREND CHART
    # --------------------------------------------------------

    required_chart_columns = {
        "Year",
        "Partner",
        "Value"
    }

    if required_chart_columns.issubset(
        display_df.columns
    ):

        selected_partner_count = (
            display_df["Partner"].nunique()
        )

        if selected_partner_count > 5:

            st.warning(
                "Trend over time is hidden because "
                f"{selected_partner_count} partners are selected. "
                "Select five or fewer partners to show the chart."
            )

        else:

            st.subheader("Trend over time")

            trend_df = display_df.copy()

            # Ensure that the chart always has a Flow column
            if "Flow" not in trend_df.columns:
                trend_df["Flow"] = "Total"

            # Flow is not included in Component.
            # It will be displayed as separate side-by-side columns.
            component_dimensions = []

            if (
                "Service item" in trend_df.columns
                and trend_df["Service item"].nunique() > 1
            ):
                component_dimensions.append(
                    "Service item"
                )

            if (
                "Unit" in trend_df.columns
                and trend_df["Unit"].nunique() > 1
            ):
                component_dimensions.append(
                    "Unit"
                )

            if component_dimensions:

                trend_df["Component"] = (
                    trend_df[component_dimensions]
                    .fillna("")
                    .astype(str)
                    .agg(" | ".join, axis=1)
                )

            else:

                trend_df["Component"] = "Total"

            trend_df = (
                trend_df
                .groupby(
                    [
                        "Year",
                        "Partner",
                        "Flow",
                        "Component"
                    ],
                    as_index=False,
                    dropna=False
                )["Value"]
                .sum()
            )

            # Sort years chronologically
            year_order = sorted(
                trend_df["Year"]
                .dropna()
                .unique(),
                key=lambda value: int(value)
                if str(value).isdigit()
                else str(value)
            )

            partner_order = sorted(
                trend_df["Partner"]
                .dropna()
                .unique()
            )

            available_flows = list(
                trend_df["Flow"]
                .dropna()
                .unique()
            )

            flow_order = sorted(
                available_flows,
                key=lambda flow: (
                    get_flow_sort_value(flow),
                    str(flow)
                )
            )

            # Create a unique side-by-side column for every
            # partner and flow combination.
            trend_df["Column group"] = (
                trend_df["Partner"].astype(str)
                + " | "
                + trend_df["Flow"].astype(str)
            )

            column_group_order = []

            for partner in partner_order:

                for flow in flow_order:

                    combination_exists = (
                        (
                            trend_df["Partner"] == partner
                        )
                        & (
                            trend_df["Flow"] == flow
                        )
                    ).any()

                    if combination_exists:
                        column_group_order.append(
                            f"{partner} | {flow}"
                        )

            # ------------------------------------------------
            # BARS
            # ------------------------------------------------

            base_chart = (
                alt.Chart(trend_df)
                .mark_bar()
                .encode(
                    x=alt.X(
                        "Year:N",
                        title="Year",
                        sort=year_order,
                        axis=alt.Axis(
                            labelAngle=0
                        )
                    ),
                    xOffset=alt.XOffset(
                        "Column group:N",
                        sort=column_group_order,
                        title=None
                    ),
                    y=alt.Y(
                        "Value:Q",
                        title="Trade value",
                        stack="zero"
                    ),
                    color=alt.Color(
                        "Component:N",
                        title="Service component"
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "Year:N",
                            title="Year"
                        ),
                        alt.Tooltip(
                            "Partner:N",
                            title="Partner"
                        ),
                        alt.Tooltip(
                            "Flow:N",
                            title="Flow"
                        ),
                        alt.Tooltip(
                            "Component:N",
                            title="Component"
                        ),
                        alt.Tooltip(
                            "Value:Q",
                            title="Value",
                            format=",.1f"
                        )
                    ]
                )
            )

            # ------------------------------------------------
            # LABELS ABOVE THE COLUMNS
            # ------------------------------------------------

            label_df = (
                trend_df
                .groupby(
                    [
                        "Year",
                        "Partner",
                        "Flow",
                        "Column group"
                    ],
                    as_index=False,
                    dropna=False
                )["Value"]
                .sum()
            )

            if selected_partner_count == 1:

                # With one partner, only show the flow name
                label_df["Column label"] = (
                    label_df["Flow"].astype(str)
                )

            else:

                # With several partners, show both partner and flow
                label_df["Column label"] = (
                    label_df["Partner"].astype(str)
                    + " | "
                    + label_df["Flow"].astype(str)
                )

            label_chart = (
                alt.Chart(label_df)
                .mark_text(
                    align="center",
                    baseline="bottom",
                    dy=-4,
                    fontSize=10
                )
                .encode(
                    x=alt.X(
                        "Year:N",
                        sort=year_order
                    ),
                    xOffset=alt.XOffset(
                        "Column group:N",
                        sort=column_group_order
                    ),
                    y=alt.Y(
                        "Value:Q",
                        stack=None
                    ),
                    text=alt.Text(
                        "Column label:N"
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "Year:N",
                            title="Year"
                        ),
                        alt.Tooltip(
                            "Partner:N",
                            title="Partner"
                        ),
                        alt.Tooltip(
                            "Flow:N",
                            title="Flow"
                        ),
                        alt.Tooltip(
                            "Value:Q",
                            title="Total",
                            format=",.1f"
                        )
                    ]
                )
            )

            trend_chart = (
                base_chart + label_chart
            ).properties(
                height=500
            ).configure_view(
                strokeWidth=0
            )

            st.altair_chart(
                trend_chart,
                use_container_width=True
            )

    # --------------------------------------------------------
    # DATA TABLE
    # --------------------------------------------------------

    st.subheader("Selected data")

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    # --------------------------------------------------------
    # CSV DOWNLOAD
    # --------------------------------------------------------

    csv = display_df.to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        label="Download selected data as CSV",
        data=csv,
        file_name=f"{reporter_code}_{DATASET}.csv",
        mime="text/csv",
        use_container_width=False
    )

else:

    st.info(
        "Choose filters in the sidebar, then click Download Data."
    )