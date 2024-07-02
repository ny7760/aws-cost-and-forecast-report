# AWS Cost Report CDK Project

- 前日までの AWS コストとコスト予測を取得し、Slack に通知するプロジェクト。
- AWS CDK を使用して自動デプロイを行う。

## プロジェクト概要

- Lambda 関数: AWS のコスト情報を取得し、Slack にメッセージを通知する
- EventBridge: 毎週金曜日の日本時間 17:00（UTC 8:00）に Lambda 関数を実行するようスケジュールしている。

## 動作確認バージョン

- Node.js (v20.10.0)
- AWS CDK CLI (v2.147.2)
- AWS CLI
- Python 3.11

## Lambda 機能

- AWS のコストと使用量データの取得
- コスト予測の取得
- 利用金額が大きいサービストップ 5 の抽出
- GMO API から為替レート（USD/JPY）を取得し、円換算金額を計算
- 整形されたレポートの Slack への送信

## セットアップ＆デプロイ

1. 依存関係をインストール

```bash
npm install
```

2. プロジェクト直下に`.env`ファイルを作成

- SLACK_WEBHOOK_URL: Slack App の設定を行い、Webhook の URL を入力してください
- PROJECT_VALUE: Project タグに設定したい値を入力してください。未指定の場合、`CostReportProject`が設定されます。

e.g. `.env` ファイル

```
SLACK_WEBHOOK_URL=https://xxxx
PROJECT_VALUE=MyCostReportProject
```

3. CDK デプロイ

```bash
# （初回のみ）CDK bootstrap を実行
cdk bootstrap
# CDK のデプロイ
cdk deploy
```

## プロジェクト構造

```
.
├── bin/
│   └── aws-cost-report.ts  # CDKアプリケーションのエントリーポイント
├── lib/
│   └── aws-cost-report-stack.ts  # メインのCDKスタック定義
├── src/
│   └── lambda/
│       └── cost-report/
│           ├── lambda_handler.py  # Lambda関数のメインハンドラー
│           ├── Pipfile   # Python依存関係
│           └── Pipfile.lock   # Python依存関係
├── package.json
└── README.md
```

## 注意事項

- Lambda 関数は Python（外部ライブラリ利用）のため、`aws-lambda-python-alpha`を利用している
- webook の URL が未設定の場合、標準出力にメッセージを出力する

## 動作の仕様

Lambda 関数は以下表に基づいて動作する。

| today                         | get_aws_cost_data                                                                      | get_aws_cost_forecast                                                                 | Slack メッセージ上の期間                                  |
| ----------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| 月初日<br>e.g. 2024-06-01     | 前月初日〜today を API にリクエスト<br>e.g. start_date=2024-05-01, end_date=2024-06-01 | get_aws_cost_data と同じデータを表示 (リクエストしない)                               | 前月初日〜yesterday を表示<br>e.g. 2024-05-01〜2024-05-31 |
| 月初日以外<br>e.g. 2024-06-15 | 月初日〜today を API にリクエスト<br>e.g. start_date=2024-06-01, end_date=2024-06-15   | today〜翌月初日を API にリクエスト<br>e.g. start_date=2024-06-15, end_date=2024-07-01 | 月初日〜yesterday を表示<br>e.g. 2024-06-01〜2024-06-14   |

## Useful commands

- `npm run build` compile typescript to js
- `npm run watch` watch for changes and compile
- `npm run test` perform the jest unit tests
- `npx cdk deploy` deploy this stack to your default AWS account/region
- `npx cdk diff` compare deployed stack with current state
- `npx cdk synth` emits the synthesized CloudFormation template
