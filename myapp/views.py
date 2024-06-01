from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from linebot import LineBotApi, WebhookParser, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from myapp.models import user
import requests

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

line_bot_api = LineBotApi(settings.LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(settings.LINE_CHANNEL_SECRET)
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
            
            checkUser(event) #檢查用戶是否已存在於資料庫裡

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

def checkUser(event):
    user_id = event.source.user_id
    # 如果用戶未存在於資料庫中，存入user_id
    if not user.objects.filter(user_id=user_id).exists():
        user.objects.create(user_id=user_id)

def sendText(event):
    try:
        message = TextSendMessage(
            text = "我是中原資管Linebot，\n您好!"
        )
        line_bot_api.reply_message(event.reply_token, message)
    except:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="傳送文字發生錯誤!"))


def send_multicast_message(request):

    # TODO: 透過api自訂用戶群體，資料庫抓取特定群體，更新user_id
    user_ids = ['USER_ID_1', 'USER_ID_2', 'USER_ID_3']  # 使用者ID列表 FIXME: 透過api自訂用戶群體
    
    # TODO: 透過api自訂訊息
    message = TextSendMessage(text='This is a multicast message!')
    
    try:
        line_bot_api.multicast(user_ids, message)
        return JsonResponse({"status": "success", "message": "Multicast message sent successfully"})
    except Exception as e:
        return JsonResponse({"status": "error", "message": str(e)})