    // TODO: 議事録アップロード用のAPI GatewayエンドポイントURLをここに貼り付けてください
    // 例: 'https://xxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/poc/upload'
    const UPLOAD_API_ENDPOINT = 'https://xxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/poc/upload';

    // TODO: 要約一覧取得用のAPI GatewayエンドポイントURLをここに貼り付けてください
    // 例: 'https://yyyyyyyy.execute-api.ap-northeast-1.amazonaws.com/poc/summaries'
    const SUMMARIES_API_ENDPOINT = 'https://xxxxxxxxx.execute-api.ap-northeast-1.amazonaws.com/poc/summaries';

    // DOM要素の取得
    // HTMLのID名に合わせて修正
    const recordButton = document.getElementById('record-button'); // 録音開始ボタン
    const stopButton = document.getElementById('stop-button');   // 録音停止ボタン
    const statusMessage = document.getElementById('status-message'); // ステータスメッセージ表示エリア
    const summariesList = document.getElementById('summariesList'); // 要約一覧表示用のul要素

    // 録音関連の変数
    let mediaRecorder;
    let audioChunks = [];
    let audioStream;

    document.addEventListener('DOMContentLoaded', () => {
        // ページ読み込み時に要約一覧を自動で取得して表示
        fetchAndDisplaySummaries();

        // 録音開始ボタンのイベントリスナー
        recordButton.addEventListener('click', async () => {
            try {
                // マイクへのアクセスを要求
                audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                
                // MediaRecorderインスタンスを作成
                // audio/webm; codecs=opus はWebM形式でOpusコーデックを使用することを示す
                mediaRecorder = new MediaRecorder(audioStream, { mimeType: 'audio/webm; codecs=opus' });
                
                // 録音データのチャンクが利用可能になったら配列に追加
                mediaRecorder.ondataavailable = (event) => {
                    if (event.data.size > 0) {
                        audioChunks.push(event.data);
                    }
                };
                
                // 録音停止時の処理
                mediaRecorder.onstop = () => {
                    // 録音されたBlobデータを作成
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm; codecs=opus' });
                    console.log('録音データ (Blob):', audioBlob);

                    // 録音データをAPI Gateway経由でLambdaに送信
                    uploadAudio(audioBlob);

                    // UIを更新
                    statusMessage.textContent = '録音を停止しました。データをアップロード中...';
                    statusMessage.style.color = '#555'; // デフォルトの色に戻す
                    recordButton.disabled = false;
                    stopButton.disabled = true;
                    
                    // 録音ストリームを停止
                    audioStream.getTracks().forEach(track => track.stop());
                    audioChunks = []; // チャンク配列をリセット
                };

                // 録音開始
                mediaRecorder.start();
                
                // UIを更新
                statusMessage.textContent = '録音中... (マイクに向かって話してください)';
                statusMessage.style.color = '#007aff'; // 録音中の色
                recordButton.disabled = true;
                stopButton.disabled = false;
                console.log('録音を開始しました。');

            } catch (err) {
                console.error('マイクへのアクセスに失敗しました:', err);
                statusMessage.textContent = 'エラー: マイクへのアクセスが必要です。';
                statusMessage.style.color = 'red';
            }
        });

        // 録音停止ボタンのイベントリスナー
        stopButton.addEventListener('click', () => {
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                mediaRecorder.stop();
                console.log('録音を停止します。');
            }
        });
    });

    /**
     * 録音データをAPI Gatewayにアップロードする関数
     * @param {Blob} audioBlob - 録音された音声データ
     */
    async function uploadAudio(audioBlob) {
        statusMessage.textContent = 'ファイルをアップロード中...';
        statusMessage.style.color = '#555';
        
        try {
            // FormDataオブジェクトを作成
            const formData = new FormData();
            // ファイル名にタイムスタンプを付けて一意にする
            const fileName = `meeting-audio-${Date.now()}.webm`;
            formData.append('audio', audioBlob, fileName);
            
            // API Gatewayへのリクエスト
            const response = await fetch(UPLOAD_API_ENDPOINT, {
                method: 'POST',
                // FormDataを使用する場合、'Content-Type'ヘッダーはfetchが自動で設定してくれる（例: multipart/form-data）
                body: formData,
            });

            if (!response.ok) {
                // エラーレスポンスの本文を読み取る
                const errorText = await response.text();
                throw new Error(`サーバーエラー: ${response.status} ${response.statusText} - ${errorText}`);
            }

            const result = await response.json();
            console.log('アップロード成功:', result);

            statusMessage.textContent = '録音データのアップロードが完了しました。文字起こしと要約が進行中です。';
            statusMessage.style.color = 'orange'; // 処理中の色

            // 要約が完了するのを待つためのポーリング処理（簡略版）
            // 実際はS3イベント通知+WebSocketなどでリアルタイム更新する方が良いが、
            // 今回はシンプルに一定時間後に一覧を再取得する
            // DynamoDBへの保存は非同期で時間がかかるため、少し長めに待つ
            setTimeout(() => {
                console.log("ポーリング：要約一覧を再読み込みします。");
                fetchAndDisplaySummaries();
                statusMessage.textContent = '要約一覧を更新しました。';
                statusMessage.style.color = 'green';
            }, 15000); // 15秒後に一覧を再読み込み
            
        } catch (error) {
            console.error('アップロードに失敗しました:', error);
            statusMessage.textContent = `アップロードに失敗しました。詳細: ${error.message}`;
            statusMessage.style.color = 'red';
        }
    }

    /**
     * DynamoDBから要約一覧を取得して表示する関数
     */
    async function fetchAndDisplaySummaries() {
        console.log("Fetching summaries from DynamoDB...");
        summariesList.innerHTML = '<p>要約を読み込み中...</p>'; // 読み込み中に表示するメッセージ

        try {
            const response = await fetch(SUMMARIES_API_ENDPOINT);
            if (!response.ok) {
                throw new Error(`Failed to fetch summaries: ${response.status} - ${await response.text()}`);
            }
            const summaries = await response.json();
            console.log("Summaries fetched:", summaries);

            // 既存のリストをクリア
            summariesList.innerHTML = '';

            if (summaries.length === 0) {
                summariesList.innerHTML = '<p>まだ要約された議事録はありません。</p>';
                return;
            }

            // リストを生成して表示
            summaries.forEach(summaryItem => {
                const li = document.createElement('li');
                // 日付を整形して表示
                const createdAt = new Date(summaryItem.created_at).toLocaleString('ja-JP', {
                    year: 'numeric', month: '2-digit', day: '2-digit',
                    hour: '2-digit', minute: '2-digit', second: '2-digit'
                });
                li.innerHTML = `
                    <h4>${createdAt}</h4>
                    <p>${summaryItem.summary}</p>
                    <small>ID: ${summaryItem.meeting_id}</small>
                `;
                summariesList.appendChild(li);
            });

        } catch (error) {
            console.error("Error fetching summaries:", error);
            summariesList.innerHTML = `<p style="color: red;">要約の取得に失敗しました。${error.message}</p>`;
        }
    }