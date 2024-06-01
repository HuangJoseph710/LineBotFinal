from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt

from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ConfirmTemplate, PostbackTemplateAction, PostbackEvent, TemplateSendMessage
from urllib.parse import parse_qsl

import requests
import time
from openai import OpenAI, OpenAIError

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

# 設置 LineBot 和 OpenAI 配置
line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)
ASSISTANT_ID = settings.ASSISTANT_ID
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# 用戶狀態
user = {}

@csrf_exempt
def callback(request):
    if request.method == 'POST':
        signature = request.META['HTTP_X_LINE_SIGNATURE']
        body = request.body.decode('utf-8')
        try:
            events = parser.parse(body, signature)
        except InvalidSignatureError:
            return HttpResponseForbidden()
        except LineBotApiError:
            return HttpResponseBadRequest()
        
        for event in events:
            if isinstance(event, MessageEvent):
                if isinstance(event.message, TextMessage):
                    mtext = event.message.text
                    user_id = event.source.user_id
                    if mtext == "@傳送文字":
                        sendText(event)
                    elif user.get(user_id) == 'asking_question':  # 如果用戶在問題狀態，處理問題
                        user[user_id] = None  # 清除狀態
                        get_answer_from_openai(user_id, mtext)
                    elif mtext == "@詢問問題":
                        user[user_id] = 'asking_question'
                        askQuestion(event)
                    else:
                        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=mtext))
            if isinstance(event, PostbackEvent):
                backdata = dict(parse_qsl(event.postback.data))
                if backdata.get('action') == 'yes':
                    user_id = event.source.user_id
                    user[user_id] = 'asking_question'
                    askQuestion(event)
                if backdata.get('action') == 'no':
                    # 這裡可以換成我們做的總模板
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="謝謝您的使用～🫶🏻"))

        return HttpResponse()
    else:
        return HttpResponseBadRequest()

def sendText(event):
    try:
        message = TextSendMessage(
            text="我是中原資管Linebot，\n您好!"
        )
        line_bot_api.reply_message(event.reply_token, message)
    except LineBotApiError:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="傳送文字發生錯誤!"))

# RAG回答
def askQuestion(event):
    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text='❓請輸入您的問題：'))
    except LineBotApiError:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text='詢問發生錯誤'))

def get_answer_from_openai(user_id, user_question):
    try:
        # 呼叫 OpenAI API
        thread = client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": user_question + "請列點回答",
                }
            ]
        )

        run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=ASSISTANT_ID)
        print(f"Run Created: {run.id}")

        while run.status != "completed":
            run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            print(f" Run Status: {run.status}")
            line_bot_api.push_message(user_id, TextSendMessage(text='🔎正在搜尋答案中，請稍候...'))
            if run.status == "completed":
                line_bot_api.push_message(user_id, TextSendMessage(text='✅已成功搜尋到答案，正在生成回應...'))
            time.sleep(15)  # 暫停15s

        messages_response = client.beta.threads.messages.list(thread_id=thread.id)
        messages = messages_response.data

        latest_message = messages[0]
        response_text = latest_message.content[0].text.value
        response_text = process_text(response_text)

        line_bot_api.push_message(user_id, TextSendMessage(text=response_text))

        # 詢問是否要繼續問答
        message = TemplateSendMessage(
            alt_text='確認',
            template=ConfirmTemplate(
                text='是否繼續提問？',
                actions=[
                    PostbackTemplateAction(
                        label="是",
                        data='action=yes'
                    ),
                    PostbackTemplateAction(
                        label="否",
                        data='action=no'
                    ),
                ]
            )
        )
        line_bot_api.push_message(user_id, message)
    except OpenAIError as e:
        print(f"Error: {e}")
        # line_bot_api.push_message(user_id, TextSendMessage(text='取得回答時發生錯誤'))
    except LineBotApiError as e:
        print(f"LineBotApiError: {e}")

# 處理 openai 的回覆內容，過濾資料來源與實現換行
def process_text(text):
    result = ""
    skip = False
    for char in text:
        if char == '【':
            skip = True
        elif char == '】':
            skip = False
        elif char == '*' or char == '。':
            if not skip:
                if char == '。':
                    result += char + '\n'
        elif not skip:
            result += char
    return result
