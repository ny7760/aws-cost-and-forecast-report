import calendar
import datetime
import logging
import os
from typing import TypedDict

import boto3
import requests
from botocore.exceptions import BotoCoreError, ClientError

GMOCOIN_API_ENDPOINT = "https://forex-api.coin.z.com/public/v1/ticker"
DEFAULT_EXCHANGE_RATE = 150.0
DATE_FORMAT = "%Y-%m-%d"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Type definitions
class UnblendedCost(TypedDict):
    Amount: str
    Unit: str


class Metrics(TypedDict):
    UnblendedCost: UnblendedCost


class CostItem(TypedDict):
    Keys: list[str]
    Metrics: Metrics


class Dates(TypedDict):
    today: str
    yesterday: str
    start_of_next_month: str
    start_date: str
    is_first_day: bool


def get_account_info() -> tuple[str, str]:
    """
    AWSアカウントIDとエイリアスを取得する。

    return:
    アカウントIDとエイリアスのタプル
    """
    client = boto3.client("sts")
    account_id = client.get_caller_identity()["Account"]

    client = boto3.client("iam")
    aliases = client.list_account_aliases()["AccountAliases"]
    account_alias = aliases[0] if aliases else "N/A"

    return account_id, account_alias


def get_dates() -> Dates:
    """
    現在の日付に基づいて、コスト計算に必要な日付情報を取得する。

    return:
    - today: 今日の日付
    - yesterday: 昨日の日付
    - start_of_next_month: 来月の初日
    - start_date: コスト計算の開始日（月初日または前月初日）
    - is_first_day: 今日が月初日かどうかのフラグ
    """

    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    if today.day == 1:
        is_first_day = True
        prev_month = today.replace(day=1) - datetime.timedelta(days=1)
        start_of_prev_month = prev_month.replace(day=1)
        # get_cost_and_usage の API では、start_date < end_dateでリクエストする必要があるため、
        # today が 月初日の場合は、前月初日を start_date に設定する
        start_date = start_of_prev_month
    else:
        is_first_day = False
        start_of_month = today.replace(day=1)
        start_date = start_of_month

    # get_cost_and_usage のAPI仕様上、start_date ≦ x < end_date であり、
    # end_date は計算期間に含まれてないため、取得したい期間末の翌日（＝月初日）を設定する必要がある。
    # ref. https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html#API_GetCostAndUsage_RequestSyntax
    _, last_day = calendar.monthrange(today.year, today.month)
    end_of_month = today.replace(day=last_day)
    start_of_next_month = end_of_month + datetime.timedelta(days=1)

    return {
        "today": today.strftime(DATE_FORMAT),
        "yesterday": yesterday.strftime(DATE_FORMAT),
        "start_of_next_month": start_of_next_month.strftime(DATE_FORMAT),
        "start_date": start_date.strftime(DATE_FORMAT),
        "is_first_day": is_first_day,
    }


def get_aws_cost_usage(start_date: str, end_date: str, group_by: bool = False) -> dict:
    """
    指定された期間のAWSコストと使用量データを Cost Explorer API を使って取得する。
    ref. https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ce/client/get_cost_and_usage.html

    params:
    - start_date: 開始日（YYYY-MM-DD形式）
    - end_date: 終了日（YYYY-MM-DD形式）
    - group_by: サービス別にグループ化するかどうかのフラグ

    return:
    get_cost_and_usage APIからのレスポンス（dict）
    """

    client = boto3.client("ce")
    params = {
        "TimePeriod": {"Start": start_date, "End": end_date},
        "Granularity": "MONTHLY",
        "Metrics": ["UnblendedCost"],
    }
    if group_by:
        params["GroupBy"] = [{"Type": "DIMENSION", "Key": "SERVICE"}]

    logger.info(f"Calling cost and usage API from {start_date} to {end_date}")

    try:
        response = client.get_cost_and_usage(**params)
        logger.info("Successfully retrieved cost and usage data from AWS")
        return response
    except (BotoCoreError, ClientError) as error:
        logger.error(f"Failed to retrieve cost and usage data from AWS: {error}")
        raise


def get_aws_cost_forecast(start_date: str, end_date: str) -> dict:
    """
    指定された期間のAWSコスト予測を、Cost Explorer API を使って取得する。
    ref. https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ce/client/get_cost_forecast.html

    params:
    - start_date: 予測開始日（YYYY-MM-DD形式）
    - end_date: 予測終了日（YYYY-MM-DD形式）

    return:
    get_cost_forecastからのレスポンス（dict）
    """

    client = boto3.client("ce")
    params = {
        "TimePeriod": {"Start": start_date, "End": end_date},
        "Granularity": "MONTHLY",
        "Metric": "UNBLENDED_COST",
    }

    logger.info(f"Calling cost forecast API from {start_date} to {end_date}")
    try:
        response = client.get_cost_forecast(**params)
        logger.info("Successfully retrieved cost forecast from AWS")
        return response
    except (BotoCoreError, ClientError) as error:
        logger.error(f"Failed to retrieve cost forecast from AWS: {error}")
        raise


def get_exchange_rate() -> float:
    """
    GMO Coin APIから最新の為替レート（USD/JPY）を取得する。
    ref. https://api.coin.z.com/fxdocs/?python#public-api
    エラーが発生した場合はデフォルトのレートを返す。

    return:
    USD/JPYの為替レート（float）
    """

    try:
        response = requests.get(GMOCOIN_API_ENDPOINT)
        response.raise_for_status()
        data = response.json()
        if data.get("status") != 0:
            raise ValueError("Invalid response status")
        usd_jpy_data = next(
            (x for x in data.get("data", []) if x.get("symbol") == "USD_JPY"), None
        )
        # ask を使っている理由は特に無し。日本円は目安なのでざっくりの値ならなんでも良い
        rate = float(usd_jpy_data.get("ask")) if usd_jpy_data else DEFAULT_EXCHANGE_RATE
        logger.info(f"Successfully retrieved exchange rate: {rate}")
        return rate
    except (requests.RequestException, ValueError, TypeError) as error:
        logger.error(f"Failed to retrieve exchange rate, using default: {error}")
        return DEFAULT_EXCHANGE_RATE


def convert_usd_to_jpy(rate: float, amount: float) -> int:
    """
    米ドルを日本円に変換する。

    params:
    - rate: 為替レート
    - amount: 米ドル金額

    return:
    日本円金額（整数、小数点以下切り捨て）
    """

    return int(rate * amount)


def get_cost_data(
    dates: Dates, include_tax: bool = False
) -> tuple[float, list[CostItem]]:
    """
    指定された日付範囲のAWSコストデータを取得する。

    params:
    - dates: 日付情報を含む辞書
    - include_tax: Taxをランキングに含めるかどうか（デフォルトはFalse）

    return:
    - 総コスト（USD）
    - 利用額トップ5のAWSサービスリスト
    """

    try:
        usage_by_services = get_aws_cost_usage(
            dates["start_date"], dates["today"], group_by=True
        )
        total_usage = get_aws_cost_usage(dates["start_date"], dates["today"])

        costs = usage_by_services.get("ResultsByTime", [{}])[0].get("Groups", [])

        if not include_tax:
            costs = [cost for cost in costs if cost.get("Keys")[0] != "Tax"]

        top5_costs = sorted(
            costs,
            key=lambda x: float(x["Metrics"]["UnblendedCost"]["Amount"]),
            reverse=True,
        )[:5]

        total_cost_usd = float(
            total_usage.get("ResultsByTime", [{}])[0]
            .get("Total", {})
            .get("UnblendedCost", {})
            .get("Amount", 0)
        )

        return total_cost_usd, top5_costs
    except Exception as error:
        logger.error(f"Failed to get cost data: {error}")
        raise


def get_forecast_data(dates: Dates, total_cost_usd: float) -> float:
    """
    AWSのコスト予測データを取得する。
    月初日の場合は、総コストをそのまま予測値として使用する。

    params:
    - dates: 日付情報を含む辞書
    - total_cost_usd: 現在の総コスト（USD）

    return:
    予測コスト（USD）
    """

    if dates["is_first_day"]:
        logger.info("First day of the month, using total cost as forecast")
        return total_cost_usd
    else:
        # start_date = end_date の場合AWSのAPIでエラーが出るため、
        # todayが月初日以外の場合のみ予測金額を取得
        try:
            forecast_response = get_aws_cost_forecast(
                dates["today"], dates["start_of_next_month"]
            )
            return float(forecast_response.get("Total", {}).get("Amount", 0))
        except Exception as error:
            logger.error(f"Failed to get forecast data: {error}")
            raise


def format_cost_message(
    account_id: str,
    account_alias: str,
    display_start_date: str,
    display_end_date: str,
    total_cost_usd: float,
    total_cost_jpy: int,
    forecast_cost_usd: float,
    forecast_cost_jpy: int,
    exchange_rate: float,
    top5_costs: list[CostItem],
) -> str:
    """
    コスト情報を整形して Slack 通知用のメッセージ文字列を作成します。

    params:
    - account_id: アカウントID
    - account_alias: アカウントエイリアス
    - display_start_date: 表示用開始日
    - display_end_date: 表示用終了日
    - total_cost_usd: 総コスト（USD）
    - total_cost_jpy: 総コスト（JPY）
    - forecast_cost_usd: 予測コスト（USD）
    - forecast_cost_jpy: 予測コスト（JPY）
    - exchange_rate: 為替レート
    - top5_costs: トップ5のコスト項目リスト

    return:
    整形されたメッセージ文字列
    """

    """Format the cost message."""
    message = f"""
アカウント: {account_alias} ({account_id})
期間: {display_start_date} - {display_end_date}

利用額: {total_cost_usd:,.2f} USD / {total_cost_jpy:,} 円
予想金額: {forecast_cost_usd:,.2f} USD / {forecast_cost_jpy:,} 円
* 為替レート: 1 USD = {exchange_rate:.2f} 円

Top5:
"""
    for i, cost in enumerate(top5_costs, start=1):
        amount = float(
            cost.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", 0)
        )
        service = cost.get("Keys")[0]
        message += f"{i}. {amount:,.2f} USD: {service}\n"

    return message


def send_message_to_slack(message: str) -> None:
    """
    指定されたメッセージをSlackに送信する。
    SLACK_WEBHOOK_URLが設定されていない場合は、コンソールに出力する。

    params:
    - message: 送信するメッセージ文字列
    """
    if SLACK_WEBHOOK_URL:
        try:
            response = requests.post(SLACK_WEBHOOK_URL, json={"text": message})
            response.raise_for_status()
            logger.info("Successfully sent message to Slack")
        except requests.RequestException as error:
            logger.error(f"Failed to send message to Slack: {error}")
    else:
        logger.info("SLACK_WEBHOOK_URL not set, printing message to console")
        print(message)


def main(event, context) -> None:
    """
    - 前日までのAWSコストデータと予測金額を取得し、Slackに通知する。
    - 参考として、円換算した金額とトップ5のコスト項目も表示する。
    """

    try:
        include_tax = event.get("include_tax", False)

        dates = get_dates()
        account_id, account_alias = get_account_info()

        total_cost_usd, top5_costs = get_cost_data(dates, include_tax)

        exchange_rate = get_exchange_rate()
        total_cost_jpy = convert_usd_to_jpy(exchange_rate, total_cost_usd)

        forecast_cost_usd = get_forecast_data(dates, total_cost_usd)
        forecast_cost_jpy = convert_usd_to_jpy(exchange_rate, forecast_cost_usd)

        message = format_cost_message(
            account_id,
            account_alias,
            dates["start_date"],
            dates["yesterday"],
            total_cost_usd,
            total_cost_jpy,
            forecast_cost_usd,
            forecast_cost_jpy,
            exchange_rate,
            top5_costs,
        )
        send_message_to_slack(message)
        logger.info("Script completed successfully")
    except Exception as error:
        logger.error(f"An error occurred during script execution: {error}")
