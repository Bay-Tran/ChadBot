# -*- coding: UTF-8 -*-

import time, re, random, os, sys
import threading
from queue import Queue
import json
import sqlite3

from fbchat import Client
from fbchat.models import *

import datamuse
from utils import *

import database


def response_loop():
    while True:
        to_send = responses.get()
        
        text=to_send[0]
        
        if type(text) == str:
            text = Message(text=text)
        
        thread_id=to_send[1]
        thread_type=to_send[2]
        
        chad.setTypingStatus(TypingStatus.TYPING, thread_id=thread_id, thread_type=thread_type)

        time.sleep(random.random() + 0.5)
        
        try:
            chad.send(text, thread_id=thread_id, thread_type=thread_type)
        except Exception as e:
            print("Error sending message: ", e)
        
        
        chad.setTypingStatus(TypingStatus.STOPPED, thread_id=thread_id, thread_type=thread_type)


def get_name(self, author_id, thread_id, thread_type):
    user = self.fetchUserInfo(author_id)[author_id]
    
    #cache this, update on onNicknameChanged
    nicknames = {}
    nicknames[user.uid] = user.nickname
    if thread_type == ThreadType.GROUP:
        nicknames = self.fetchGroupInfo(thread_id)[thread_id].nicknames
        print(nicknames)
    
    
    nickname = nicknames.get(user.uid)
    
    
    name = "@"+(nickname or user.first_name)
    
    return name

def parse_message(self, mid, author_id, message, message_object, thread_id, thread_type, ts, metadata, msg):
    if author_id == self.uid:
        return
    
    mute_ts = DB.get_timeout(thread_id, "mute")
    
    diff = ts - mute_ts
    
    #if it's been less than 10 minutes since chad was muted for this channel
    if diff <= (10 * 60 * 1000):
        return
    
    text = message_object.text
    
    if not text:
        return
    
    gre = Re()

    if gre.match(virgin_re, text.lower()):
        word = gre.last_match.group(1).strip()
        
        chadlier = DB.get_chad(word)
        
        if not chadlier:
            
            synonyms = datamuse.get_synonyms(word)

            try:
                chadlier = random.choice(synonyms)
            except IndexError:
                return

        if chadlier:
            
            if chadlier == "{{CHAD}}":
                response = "{} IS AS CHADLY AS IT GETS".format(word.upper())
            else:
                response = "THE CHAD {}".format(chadlier.upper())

            responses.put((response, thread_id, thread_type))
    elif text.lower() == "f":
        
        last_f = DB.get_timeout(thread_id, "f")

        diff = ts - last_f
        
        F_RATE = 20000
        
        if diff > F_RATE:
            responses.put(("F", thread_id, thread_type))
        else:
            return
        
        DB.set_timeout(thread_id, "f", ts)
        
        print("ts = "+str(ts))
    elif text == "STOP IT CHAD":
        self.send(Message(text="Ouch!"), thread_id, thread_type)
        
        DB.set_timeout(thread_id, "mute", ts)
    elif text == "BEGONE CHAD!":
        exit_message = "Chad strides into the sunset, never to be seen again"
        self.send(Message(text=exit_message, mentions=[Mention(self.uid, 0, len(exit_message))]), thread_id, thread_type)
        self.removeUserFromGroup(self.uid, thread_id)
    elif author_id == config["facebook"]["owner_uid"] and text.lower() == "restart chad":
        print("Restarting!")
        self.send(Message(text="*gives firm handshake* Chad will be right back."), thread_id, thread_type)
        
        #May not be portable
        os.execv(sys.executable, ['python3'] + sys.argv)
    elif gre.search(dice_re, text.lower()):
        match = gre.last_match
        num_dice = int(match.group(1) or '1')
        dice_type = int(match.group(2))
        
        if match.group(3):
            constant = int(match.group(4))
            opr = match.group(3)
        else:
            constant = 0
            opr = "+"
        
        total = 0
        if dice_type > 0 and dice_type < 10000 and num_dice > 0 and num_dice <= 200:
            for i in range(num_dice):
                total += random.randint(1, dice_type)
        else:
            return
            
        if opr == "+":
            total += constant
        else:
            total -= constant
        
        name = get_name(self, author_id, thread_id, thread_type)
        
        try:
            #gets the rest of the text following the end of the roll command
            reason = text[match.span()[1]:]
        except IndexError:
            reason = ""
        
        response = name + " rolled " + str(total) + reason
        
        responses.put((Message(text=response, mentions=[Mention(author_id, 0, len(name))]), thread_id, thread_type))
    elif gre.search(coin_re, text.lower()):
        match = gre.last_match
        
        try:
            num_coins = int(match.group(1))
        except ValueError:
            num_coins = 1
        
        if num_coins == 1:
            result = random.choice(("heads", "tails"))
        elif 0 < num_coins <= 25:
            result = "["
            
            for i in range(num_coins):
                result += random.choice(("H", "T")) + ","
            
            result = result[:-1] + "]"
        else:
            return
        
        name = get_name(self, author_id, thread_id, thread_type)
        
        response = name + " got " + result
        
        responses.put((Message(text=response, mentions=[Mention(author_id, 0, len(name))]), thread_id, thread_type))
    elif gre.match("!setchad ([\w ]+?) *, *([\w ]+)", text.lower()):
        virgin = gre.last_match.group(1)
        chad = gre.last_match.group(2)
        
        if len(virgin) and len(chad):
            DB.set_chad(virgin, chad)
    elif "69" in text or "420" in text:
        responses.put(("nice", thread_id, thread_type))
        
        
class Chad(Client):
    active = True
    #to do: spawn a new thread for every response
    def onMessage(self, mid, author_id, message, message_object, thread_id, thread_type, ts, metadata, msg):
        self.markAsDelivered(author_id, thread_id)
        thread = threading.Thread(target=parse_message, args=(self, mid, author_id, message, message_object, thread_id, thread_type, ts, metadata, msg))
        thread.daemon = True
        
        thread.start()
    
    def onFriendRequest(self, from_id, msg):
        print("Got friend request from "+str(from_id))
        self.friendConnect(from_id)
    
    def onPeopleAdded(self, mid=None, added_ids=None, author_id=None, thread_id=None, ts=None, msg=None):
        if self.uid in added_ids:
            responses.put(("CHAD IS HERE", thread_id, ThreadType.GROUP))

    
if __name__ == '__main__':
    with open("conf.json", "r") as f:
        config = json.load(f)

    owner_uid = config["facebook"]["owner_uid"]

    virgin_re = re.compile("the virgin ([\w\s]*)");
    dice_re = re.compile("roll (?:a )?([0-9]*)d([0-9]+)(?: *([+-]) *([0-9]+))?")
    coin_re = re.compile("flip (a|\d+) coin(?:s?)")
    
    responses = Queue()
    
    DB = database.Database("chad.sqlite3")
    
    database_thread = threading.Thread(target = DB.loop)
    database_thread.daemon = True
    database_thread.start()
    

    response_thread = threading.Thread(target=response_loop)
    response_thread.daemon = True

    response_thread.start()

   
    
    chad = Chad(config["facebook"]["email"], config["facebook"]["password"])
    
    chad.listen()

    chad.logout()
