from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt

from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ConfirmTemplate,
    PostbackTemplateAction, PostbackEvent, TemplateSendMessage,
    FlexSendMessage, BubbleContainer, BoxComponent, TextComponent
)
from urllib.parse import parse_qsl

import requests
import time
from openai import OpenAI, OpenAIError

import json
from firebase import firebase

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

# 設置 LineBot 和 OpenAI 配置
line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)
ASSISTANT_ID = settings.ASSISTANT_ID
client = OpenAI(api_key=settings.OPENAI_API_KEY)
firebase_url = settings.FIREBASE_URL

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
                    elif mtext == "@模擬面試": #進入模擬面試狀態
                        start_interview(event) 
                    elif user.get(user_id) == 'interview':
                        process_interview(event, mtext)
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
                if backdata.get('action') == 'interview_yes':
                    user_id = event.source.user_id
                    user[user_id] = 'interview'
                    continue_interview(event)
                if backdata.get('action') == 'interview_no':
                    user_id = event.source.user_id
                    clear_chat_history(user_id)
                    # 這裡可以換成我們做的總模板
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="謝謝您的使用～🫶🏻"))

        return HttpResponse()
    else:
        return HttpResponseBadRequest()


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

# 開始模擬面試
def start_interview(event):
    user_id = event.source.user_id
    fdb = firebase.FirebaseApplication(firebase_url, None)
    user_chat_path = f'chat/{user_id}'
    
    introduction = (
        "您好，我是專門幫助學生準備中原大學資管系面試的模擬面試助理。"
        "我將會提出面試問題，並根據您的回答給予評分、評語和建議。"
        "每次您回答後，我會詢問是否需要繼續提問。"
    )
    introduction_msg=TextSendMessage(text=introduction)

    messages = [
        {"role": "system", "content": "你是繁體中文人工智慧助理，幫助學生準備中原大學資管系的面試。您將提出問題、評估他們的答案、提供回饋並提出改進建議。\n請以以下固定格式提供回應:\n1. 評分：[例如：優秀/中規中矩/待加強之類的表述方式]\n2. 評語：[描述文字]\n3. 建議回達內容：[描述文字]"},
        {"role": "user", "content": "出題"}
    ]
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        max_tokens=400,
        temperature=0.5,
        messages=messages
    )
    
    ai_msg = response.choices[0].message.to_dict()['content'].replace('\n', '')
    messages.append({"role": "assistant", "content": ai_msg})
    fdb.put_async(user_chat_path, None, messages)
    
    reply_msg = TextSendMessage(text=ai_msg)
    message = [introduction_msg, reply_msg]
    line_bot_api.reply_message(event.reply_token, message)
    user[user_id] = 'interview'

# 模擬面試助理進行打分
def process_interview(event, user_answer):
    user_id = event.source.user_id
    fdb = firebase.FirebaseApplication(firebase_url, None)
    user_chat_path = f'chat/{user_id}'
    chatgpt = fdb.get(user_chat_path, None)

    if chatgpt is None:
        chatgpt = []

    chatgpt.append({"role": "user", "content": user_answer})
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        max_tokens=400,
        temperature=0.5,
        messages=chatgpt
    )
    
    ai_msg = response.choices[0].message.to_dict()['content'].replace('\n', '')
    print(ai_msg)
    
    # 提取三個內容
    score = ai_msg.split('2. 評語：')[0].split('1. 評分：')[1].strip()
    comment = ai_msg.split('3. 建議回答內容：')[0].split('2. 評語：')[1].strip()
    suggestion = ai_msg.split('3. 建議回答內容：')[1].strip()
    
    chatgpt.append({"role": "assistant", "content": ai_msg})
    fdb.put_async(user_chat_path, None, chatgpt)
    
    # 使用 BubbleContainer 包裝三個區塊，並設置 wrap=True 來處理文字換行
    bubble = BubbleContainer(
        body=BoxComponent(
            layout='vertical',
            contents=[
                BoxComponent(
                    layout='vertical',
                    contents=[
                        TextComponent(text='評分', weight='bold', size='xl', wrap=True),
                        TextComponent(text=score, size='sm', margin='md', wrap=True)
                    ]
                ),
                BoxComponent(
                    layout='vertical',
                    contents=[
                        TextComponent(text='評語', weight='bold', size='xl', wrap=True),
                        TextComponent(text=comment, size='sm', margin='md', wrap=True)
                    ]
                ),
                BoxComponent(
                    layout='vertical',
                    contents=[
                        TextComponent(text='建議回答內容', weight='bold', size='xl', wrap=True),
                        TextComponent(text=suggestion, size='sm', margin='md', wrap=True)
                    ]
                )
            ]
        )
    )
    
    reply_msg = FlexSendMessage(alt_text='結果', contents=bubble)
    line_bot_api.reply_message(event.reply_token, reply_msg)
    
    ask_continue(event)

# 詢問用戶是否繼續提問
def ask_continue(event):
    message = TemplateSendMessage(
        alt_text='確認',
        template=ConfirmTemplate(
            text='是否繼續提問？',
            actions=[
                PostbackTemplateAction(
                    label="是",
                    data='action=interview_yes'
                ),
                PostbackTemplateAction(
                    label="否",
                    data='action=interview_no'
                ),
            ]
        )
    )
    line_bot_api.push_message(event.source.user_id, message)

# 請模擬面試助理繼續提問下一個問題
def continue_interview(event):
    user_id = event.source.user_id
    fdb = firebase.FirebaseApplication(firebase_url, None)
    user_chat_path = f'chat/{user_id}'
    chatgpt = fdb.get(user_chat_path, None)

    if chatgpt is None:
        chatgpt = []

    chatgpt.append({"role": "user", "content": "請出下一題"})
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        max_tokens=400,
        temperature=0.5,
        messages=chatgpt
    )
    
    ai_msg = response.choices[0].message.to_dict()['content'].replace('\n', '')
    chatgpt.append({"role": "assistant", "content": ai_msg})
    fdb.put_async(user_chat_path, None, chatgpt)
    
    reply_msg = TextSendMessage(text=ai_msg)
    line_bot_api.push_message(user_id, reply_msg)

# 清除歷史紀錄
def clear_chat_history(user_id):
    fdb = firebase.FirebaseApplication(firebase_url, None)
    user_chat_path = f'chat/{user_id}'
    fdb.delete(user_chat_path, None)
    user[user_id] = None