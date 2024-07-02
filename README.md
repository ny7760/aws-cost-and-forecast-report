# AWS Cost and Forecast Report Project

## 概要

- AWS の前日までのコスト、コスト予測を取得し、Slack にメッセージを通知する
- AWS CDK を使用してデプロイを行う
- EventBridge は、 JST で毎週金曜日の 17:00（UTC 8:00）に Lambda 関数を実行するようスケジュールしている

<div align="center">
    <img src="docs/architecture.png" alt="アーキテクチャ図" width="400" height="250">
</div>

## 動作確認バージョン

- Node.js (v20.10.0)
- AWS CDK CLI (v2.147.2)
- AWS CLI
- Python 3.11

## セットアップ＆デプロイ

1. Slack App を作成し、Webhook の URL を設定する。

2. リポジトリを clone して依存関係をインストール

```bash
npm install
```

3. プロジェクト直下に`.env`ファイルを作成

- SLACK_WEBHOOK_URL: Slack App で設定した Webhook の URL を入力してください
- PROJECT_VALUE: Project タグに設定したい値を入力してください。未指定の場合、`CostReportProject`が設定されます。

e.g. `.env` ファイル

```
SLACK_WEBHOOK_URL=https://xxxx
PROJECT_VALUE=MyCostReportProject
```

4. CDK デプロイ

```bash
# （初回のみ）CDK bootstrap を実行
cdk bootstrap
# CDK のデプロイ
cdk deploy
```

## プロジェクト構成

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

## アプリケーション仕様

### Lambda がやっていること

- AWS のコストと使用量データの取得
- コスト予測の取得
- 利用金額が大きいサービストップ 5 の抽出
- [GMO コインの API](https://api.coin.z.com/fxdocs/#outline) から為替レート（USD/JPY）を取得し、円換算した金額を計算
- Slack へ整形した情報を送信

### 仕様詳細

Lambda が稼働した日が月初日かどうかで挙動が異なります。詳細は以下の表を参照してください。

| 稼働日                        | get_aws_cost_data                                                                      | get_aws_cost_forecast                                                                 | Slack メッセージ上の期間                                  |
| ----------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| 月初日<br>e.g. 2024-06-01     | 前月初日〜today を API にリクエスト<br>e.g. start_date=2024-05-01, end_date=2024-06-01 | get_aws_cost_data と同じデータを表示 (Cost Explorer にリクエストしない)               | 前月初日〜yesterday を表示<br>e.g. 2024-05-01〜2024-05-31 |
| 月初日以外<br>e.g. 2024-06-15 | 月初日〜today を API にリクエスト<br>e.g. start_date=2024-06-01, end_date=2024-06-15   | today〜翌月初日を API にリクエスト<br>e.g. start_date=2024-06-15, end_date=2024-07-01 | 月初日〜yesterday を表示<br>e.g. 2024-06-01〜2024-06-14   |

## 注意事項

- Lambda 関数は Python の外部ライブラリ利用しているため、`aws-lambda-python-alpha`を利用しています。
- Webook の URL が未設定の場合、標準出力にメッセージを出力します。

## Useful commands

- `npm run build` compile typescript to js
- `npm run watch` watch for changes and compile
- `npm run test` perform the jest unit tests
- `npx cdk deploy` deploy this stack to your default AWS account/region
- `npx cdk diff` compare deployed stack with current state
- `npx cdk synth` emits the synthesized CloudFormation template
