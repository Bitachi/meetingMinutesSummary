import json
import boto3
import os

# DynamoDBクライアントを初期化
dynamodb_client = boto3.client('dynamodb')

# DynamoDBテーブル名を環境変数から取得（推奨）
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'MeetingMinutesSummary')

def lambda_handler(event, context):
    print("--- Get Summaries Lambda started ---")

    try:
        # DynamoDBから全項目をスキャンして取得
        # 注意: 項目数が多い場合は、このscan_all_items関数を修正して、
        #       Pagination（ページネーション）を実装する必要があります。
        #       今回はPOCのため、単純なスキャンで実装します。
        def scan_all_items():
            items = []
            response = None
            while response is None or 'LastEvaluatedKey' in response:
                if response:
                    response = dynamodb_client.scan(
                        TableName=DYNAMODB_TABLE_NAME,
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                else:
                    response = dynamodb_client.scan(TableName=DYNAMODB_TABLE_NAME)
                items.extend(response.get('Items', []))
            return items

        # DynamoDBから全項目を取得
        all_summaries = scan_all_items()
        
        # 取得したDynamoDBの項目を整形
        # DynamoDBのデータ形式（{ 'S': 'value' }）からPythonのディクショナリに変換
        summaries_list = []
        for item in all_summaries:
            summaries_list.append({
                'meeting_id': item['meeting_id']['S'],
                'summary': item['summary']['S'],
                'created_at': item['created_at']['S']
            })
            
        print(f"Fetched {len(summaries_list)} summaries from DynamoDB.")
        
        # 作成日時でソート (新しい順)
        summaries_list.sort(key=lambda x: x['created_at'], reverse=True)

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET,OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Content-Type': 'application/json'
            },
            'body': json.dumps(summaries_list)
        }

    except Exception as e:
        print(f"--- Error in Get Summaries Lambda: {e} ---")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'message': 'Internal Server Error', 'error': str(e)})
        }