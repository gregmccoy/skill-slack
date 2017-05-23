from os.path import dirname

from adapt.intent import IntentBuilder
from mycroft.client.speech.main import handle_speak
from mycroft.skills.core import MycroftSkill
from mycroft.util.log import getLogger
from mycroft.messagebus.message import Message
import requests
import re
import json
import threading
import time
from slackclient import SlackClient

__author__ = 'gregmccoy'

LOGGER = getLogger(__name__)

class SlackSkill(MycroftSkill):
    def __init__(self):
        super(SlackSkill, self).__init__(name="SlackSkill")

        # Pull key from config file
        self.key = self.config.get('api_key')
        self.slack = SlackClient(self.key)


    def __exit__(self, exc_type, exc_value, traceback):
        print("Cleaning up")
        for thread in self.threads:
            thread.exit()


    def initialize(self):
        send_message = IntentBuilder("SendSlackMessage")\
            .require("SendSlackMessage").build()
        self.register_intent(send_message, self.handle_send_message)

        def slack_reply(message):
            try:
                text = message.data["utterance"]
                self.slack.api_call(
                  "chat.postMessage",
                  channel=self.current_user,
                  text=text
                )
            except Exception as e:
                print("Error occured: " + str(e))

        # Remove normal speech function
        self.emitter.remove_all_listeners("speak")
        self.emitter.on("speak", slack_reply)
        self.live = True

        self.threads = []
        t = threading.Thread(target=self.listen)
        self.threads.append(t)
        t.start()


    def get_user(self, recipient):
        userlist = self.slack.api_call("users.list")
        for user in userlist["members"]:
            try:
                first_name = user["profile"]["first_name"].lower()
                if recipient.lower() in first_name or recipient.lower() == first_name:
                    return user
            except:
                pass
        return None


    def get_channel(self, recipient):
        channellist = self.slack.api_call("channels.list")
        for channel in channellist["channels"]:
            try:
                channel_name = channel["name"].lower()
                if recipient.lower() in channel_name or recipient.lower() == channel_name:
                    return channel
            except:
                pass
        return None

    def listen(self):
        if self.slack.rtm_connect():
            user = self.slack.server.login_data["self"]["id"]
            while self.live:
                try:
                    message = self.slack.rtm_read()
                    if message:
                        if message[0]["type"] == "message":
                            text = message[0]["text"]
                            if user in text or user in message[0]["channel"]:
                                # if they tagged the bot in the message we want to remove that
                                text = text.replace("<@" + user + ">", "")
                                self.current_user = message[0]["channel"]
                                self.enclosure.ws.emit(Message("recognizer_loop:utterance", {'utterances': [text.strip()] }))
                except Exception as e:
                    #Connection Problems trying again in 10 seconds
                    print("Exception")
                    print(e)
                    time.sleep(5)
                time.sleep(1)


    def handle_send_message(self, message):
        utterance = message.data.get("utterance")
        utterance = utterance.split(" ")
        utterance = " ".join(utterance)

        recipient = None
        content = None

        try:
            match = re.search("(to|slack|black|message).*?(?= say|$)", utterance)
            match_str = match.group(0)
            for item in ["to ", "slack message ", "slack ", "black ", "black message "]:
                match_str = match_str.replace(item, "")
            recipient = match_str

            match = re.search("say.*?(?= to|$)", utterance)
            content = match.group(0).replace("say ", "")
        except:
            self.speak_dialog("error.message")
            return

        # When conversation is available we can ask for any missing varaibles
        #if not recipient:
        #    response = self.speak("Who should I message on slack?", expect_response=True)
        #    print(response)
        #    return

        #if not content:
        #    response = self.speak("What should I say?", expect_response=True)
        #    print(response)
        #    print("---")
        #    return

        # Check if it's user
        user = self.get_user(recipient)
        if user:
            name = user["name"]
            user = user["id"]

        # Check if it's a channel
        if not user:
            user = self.get_channel(recipient)
            if user:
                name = user["name"]
                user = "#" + user["name"]

        if user:
            self.slack.api_call(
              "chat.postMessage",
              channel=user,
              text=content
            )
            self.speak_dialog("send.message", { "user": name })
        else:
            self.speak("Could not find user or channel named {}".format(recipient))

def create_skill():
    return SlackSkill()

