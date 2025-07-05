import json
import boto3
import os
import urllib.parse
from botocore.exceptions import ClientError
from datetime import datetime
import re
import http.client
import ssl

# AWS SDK for Python (Boto3) クライアントを初期化
s3_client = boto3.client('s3')
ssm_client = boto3.client('ssm')
# DynamoDBクライアントを追加
dynamodb_client = boto3.client('dynamodb')

# DynamoDBテーブル名を環境変数から取得（推奨）
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'MeetingMinutesSummary')

# Claude API keyをParameter Storeから取得する (変更なし)
def get_claude_api_key():
    # ... (既存のコード) ...
    try:
        param_name = '/meeting-minutes-app/claude-api-key'
        response = ssm_client.get_parameter(Name=param_name, WithDecryption=True)
        return response['Parameter']['Value']
    except ClientError as e:
        print(f"Error getting parameter: {e}")
        raise e

# Claude APIを呼び出すための関数 (変更なし)
# Claude APIを呼び出すための関数
def call_claude_api(transcript_text, api_key):
    # AnthropicのAPIエンドポイント
    api_url = "https://api.anthropic.com/v1/messages"
    
    # Claudeへのプロンプト
    prompt = f"""
    You are a professional and concise meeting summarization assistant. 
    Please summarize the following meeting transcript into a clear and well-structured summary.
    Highlight key decisions, action items, and any open questions.
    
    <transcript>
    {transcript_text}
    </transcript>
    
    Provide the summary in Japanese.
    """
    
    # 修正: 'headers' 変数の定義を関数内に記述します
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    # APIリクエストのペイロード
    data = {
        "model": "claude-3-5-sonnet-20240620", # 使用モデルを指定
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}]
    }

    # Pythonの標準ライブラリでHTTPリクエストを送信
    import http.client
    import ssl
    
    conn = http.client.HTTPSConnection("api.anthropic.com", context=ssl.create_default_context())
    conn.request("POST", "/v1/messages", json.dumps(data).encode('utf-8'), headers) # 修正: json.dumps()の出力をencode
    response = conn.getresponse()
    
    if response.status != 200:
        print(f"Claude API Error: {response.status} {response.reason}")
        print(response.read().decode('utf-8'))
        raise Exception(f"Claude API call failed with status {response.status}")

    response_data = json.loads(response.read().decode('utf-8'))
    conn.close()
    
    # 応答から要約テキストを抽出
    summary_text = response_data['content'][0]['text']
    return summary_text


def lambda_handler(event, context):
    print("--- Summarizer Lambda started ---")
    
    try:
        # ... (既存のS3イベントからファイル情報を取得するコード) ...
        # 1. S3イベントからファイル情報を取得
        bucket_name = event['Records'][0]['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'])
        
        print(f"Received S3 event for file: s3://{bucket_name}/{key}")
        
        # Transcribeのジョブ名から一意なIDを取得
        # Key: transcripts/meeting-transcript-1719702229.json
        meeting_id = os.path.splitext(os.path.basename(key))[0]
        
        # 2. S3から文字起こし結果のJSONファイルを読み込む
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        transcript_json_content = response['Body'].read().decode('utf-8')
        transcript_data = json.loads(transcript_json_content)
        transcript_text = transcript_data['results']['transcripts'][0]['transcript']
        
        print("Transcript fetched successfully. Length:", len(transcript_text))

        # 3. Claude APIキーを取得
        claude_api_key = get_claude_api_key()
        
        # 4. Claudeで要約を生成
        print("Calling Claude API to generate summary...")
        summary = call_claude_api(transcript_text, claude_api_key)
        
        print("Summary generated successfully.")

        # 5. 要約結果をDynamoDBに保存する (ここから追加)
        print("Saving summary to DynamoDB...")
        
        item = {
            'meeting_id': {'S': meeting_id}, # パーティションキー
            'summary': {'S': summary},       # 要約内容
            'transcript_s3_key': {'S': key}, # 元の文字起こしファイルのS3キー
            'created_at': {'S': datetime.now().isoformat()}
        }
        
        dynamodb_client.put_item(
            TableName=DYNAMODB_TABLE_NAME,
            Item=item
        )
        
        print("Summary saved to DynamoDB successfully.")
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Summary saved to DynamoDB.'})
        }

    except Exception as e:
        print(f"--- Error in Summarizer Lambda: {e} ---")
        raise e