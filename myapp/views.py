from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt

from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import requests

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(settings.LINE_CHANNEL_SECRET)

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
                    if mtext == "@傳送文字":
                        sendText(event)
                    else:
                        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=mtext))
            # if isinstance(event, PostbackEvent):
            #     backdata = dict(parse_qsl(event.postback.data))
            #     if backdata.get("action") == "buy":
            #         sendBack_buy(event, backdata)

        return HttpResponse()
    else:
        return HttpResponseBadRequest()


def sendText(event):
    try:
        message = TextSendMessage(
            text = "我是中原資管Linebot，\n您好!"
        )
        line_bot_api.reply_message(event.reply_token, message)
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="傳送文字發生錯誤!"))