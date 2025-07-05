import json
import base64
import boto3
import os
import io
from datetime import datetime
import re # Add this import for regex

# AWS SDK for Python (Boto3) クライアントを初期化
s3_client = boto3.client('s3')
transcribe_client = boto3.client('transcribe')

# 環境変数からバケット名を取得する
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')

def lambda_handler(event, context):
    print("--- Handler started ---") # 追加したデバッグログ
    print(f"Received event: {json.dumps(event, indent=2)}")

    try:
        # 1. API GatewayからBase64エンコードされたリクエストボディを取得
        body = event.get('body')
        is_base64_encoded = event.get('isBase64Encoded', False)

        if not body:
            print("Error: Body is empty.")
            return {
                'statusCode': 400,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'message': 'Request body is empty.'})
            }

        # Base64でエンコードされている場合、デコードする
        if is_base64_encoded:
            body_bytes = base64.b64decode(body)
        else:
            # エンコードされていない場合はそのままバイトデータとして扱う
            body_bytes = body.encode('utf-8')

        # ----------------------------------------------------
        # 2. multipart/form-dataをパースしてファイルデータを抽出 (修正部分)
        # ----------------------------------------------------
        content_type_header = event.get('headers', {}).get('Content-Type') or event.get('headers', {}).get('content-type')
        if not content_type_header or 'multipart/form-data' not in content_type_header:
            print(f"Error: Content-Type is not multipart/form-data. Found: {content_type_header}")
            return {
                'statusCode': 415,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'message': 'Unsupported Media Type. Expected multipart/form-data.'})
            }

        # boundaryの抽出
        boundary = re.search(r'boundary=([^;]+)', content_type_header).group(1)
        if not boundary:
            raise ValueError("Boundary not found in Content-Type header.")
        
        # マルチパートボディをboundaryで分割
        # Note: 録音データは1つのパートなので、シンプルに処理
        parts = body_bytes.split(b'--' + boundary.encode('utf-8'))
        
        # audioパートを探す
        audio_part = None
        for part in parts:
            if b'name="audio"' in part:
                audio_part = part
                break
        
        if not audio_part:
            raise ValueError("Audio part not found in multipart body.")
            
        # ヘッダーとボディを分離
        headers, body_content = audio_part.split(b'\r\n\r\n', 1)
        
        # ファイル名をヘッダーから抽出
        file_name_match = re.search(b'filename="([^"]+)"', headers)
        if file_name_match:
            file_name = file_name_match.group(1).decode('utf-8')
        else:
            file_name = f'recorded-audio-{datetime.now().strftime("%Y%m%d%H%M%S")}.webm' # デフォルトファイル名

        file_content = body_content.strip()
        
        print(f"Parsed file: {file_name}, size: {len(file_content)} bytes")

        # ----------------------------------------------------
        # 3. 録音データをS3にアップロードする
        # ----------------------------------------------------
        s3_key = f"raw_audio/{file_name}"
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=file_content,
            ContentType='audio/webm'
        )
        print(f'Successfully uploaded file to S3: s3://{S3_BUCKET_NAME}/{s3_key}')

        # ----------------------------------------------------
        # 4. Amazon Transcribeの文字起こしジョブを開始する
        # ----------------------------------------------------
        transcription_job_name = f"meeting-transcript-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        media_file_uri = f's3://{S3_BUCKET_NAME}/{s3_key}'
        
        transcribe_client.start_transcription_job(
            TranscriptionJobName=transcription_job_name,
            LanguageCode='ja-JP',
            Media={'MediaFileUri': media_file_uri},
            OutputBucketName=S3_BUCKET_NAME,
            OutputKey=f'transcripts/{transcription_job_name}.json'
        )
        print(f"Started Transcribe job: {transcription_job_name}")

        # ----------------------------------------------------
        # 5. クライアントに成功レスポンスを返す
        # ----------------------------------------------------
        print("--- Handler finished successfully ---")
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST,OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,Content-Disposition',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'message': 'Audio uploaded and transcription job started successfully.',
                'jobName': transcription_job_name,
                'audioKey': s3_key,
            })
        }

    except Exception as e:
        print(f"--- Error occurred: {e} ---")
        # 例外が発生した場合もCORSヘッダーを返すように修正
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'message': 'Internal Server Error', 'error': str(e)})
        }