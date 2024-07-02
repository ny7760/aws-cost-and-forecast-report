import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import events = require("aws-cdk-lib/aws-events");
import targets = require("aws-cdk-lib/aws-events-targets");
import lambda = require("aws-cdk-lib/aws-lambda");
import * as iam from "aws-cdk-lib/aws-iam";
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import * as dotenv from "dotenv";
import * as path from "path";

dotenv.config({ path: path.resolve(__dirname, "../.env") });

export class AwsCostReportStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    cdk.Tags.of(this).add(
      "Project",
      process.env.PROJECT_VALUE || "CostReportProject"
    );

    // Lambda 用の IAM ロールを作成
    const lambdaRole = new iam.Role(this, "CostReporterRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "IAM role for Cost Reporter Lambda function",
    });

    // AWSLambdaBasicExecutionRole マネージドポリシーを追加
    lambdaRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName(
        "service-role/AWSLambdaBasicExecutionRole"
      )
    );

    // Cost Explorer へのアクセス権限を持つカスタムポリシーを作成
    const costExplorerPolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ["ce:GetCostAndUsage", "ce:GetCostForecast"],
      resources: ["*"], // Cost Explorer API doesn't support resource-level permissions
    });

    // カスタムポリシーをロールに追加
    lambdaRole.addToPolicy(costExplorerPolicy);

    const lambdaFn = new PythonFunction(this, "CostReporter", {
      entry: "src/lambda/cost-report",
      index: "lambda_handler.py",
      handler: "main",
      timeout: cdk.Duration.seconds(300),
      runtime: lambda.Runtime.PYTHON_3_11,
      environment: {
        SLACK_WEBHOOK_URL: process.env.SLACK_WEBHOOK_URL || "",
      },
      role: lambdaRole,
      applicationLogLevelV2: lambda.ApplicationLogLevel.INFO,
      loggingFormat: lambda.LoggingFormat.JSON,
    });

    // Run 5:00 PM JTC (8:00 AM UTC) every Friday
    // See https://docs.aws.amazon.com/lambda/latest/dg/tutorial-scheduled-events-schedule-expressions.html
    const rule = new events.Rule(this, "CostReportRule", {
      schedule: events.Schedule.expression("cron(0 8 ? * FRI *)"),
    });

    rule.addTarget(new targets.LambdaFunction(lambdaFn));
  }
}

const app = new cdk.App();
new AwsCostReportStack(app, "AwsCostReportStack");
