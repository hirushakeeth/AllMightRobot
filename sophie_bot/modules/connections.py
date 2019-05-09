import re

from sophie_bot import bot, mongodb, redis
from sophie_bot.events import register
from sophie_bot.modules.users import is_user_admin

from telethon import errors, events
from telethon.tl.custom import Button


@register(incoming=True, pattern="^[/!]connect ?(.*)")
async def connect_with_arg(event):
    user_id = event.from_id
    if not event.chat_id == user_id:
        chat = event.chat_id
        chat = mongodb.chat_list.find_one({'chat_id': int(chat)})
        print(chat)
    else:
        chat = event.message.raw_text.split(" ", 2)[1]
        if not chat[0] == '-':
            chat = mongodb.chat_list.find_one({
                'chat_nick': chat.replace("@", "")
            })
            if not chat:
                event.reply("I can't find this chat, try using chat id.")
                return
        else:
            chat = mongodb.chat_list.find_one({'chat_id': int(chat)})
            if not chat:
                await event.reply("I can't find this chat.")
                return

    chat_id = chat['chat_id']
    chat_title = chat['chat_title']

    user_chats = mongodb.user_list.find_one({'user_id': user_id})
    if user_chats and 'chats' in user_chats:
        if chat_id not in user_chats['chats']:
            await event.reply(
                "You not in the connecting group, join and write any message.")
            return

    history = mongodb.connections.find_one({'user_id': user_id})
    if not history:
        mongodb.connections.insert_one({
            'user_id': user_id,
            'chat_id': chat_id,
            'btn1': chat_id,
            'btn2': None,
            'btn3': None,
            'btn4': None,
            'btn5': None,
            'updated': 3
        })
    else:
        btn1 = history['btn1']
        btn2 = history['btn2']
        btn3 = history['btn3']
        updated = history['updated']

        if history['updated'] == 1 and chat_id != history['btn2'] and chat_id != history['btn3']:
            btn1 = chat_id
            updated = 2
        elif history['updated'] == 2 and chat_id != history['btn1'] and chat_id != history['btn3']:
            btn2 = chat_id
            updated = 3
        elif history['updated'] >= 3 and chat_id != history['btn2'] and chat_id != history['btn1']:
            btn3 = chat_id
            updated = 1

        mongodb.connections.delete_one({'_id': history['_id']})

        mongodb.connections.insert_one({
            'user_id': user_id,
            'chat_id': chat_id,
            'btn1': btn1,
            'btn2': btn2,
            'btn3': btn3,
            'updated': updated
        })

    redis.set('connection_cache_{}'.format(user_id), chat_id)

    text = "Successfully connected to **{}**!".format(chat_title)
    if event.chat_id == user_id:
        await event.reply(text)
    else:
        try:
            await bot.send_message(user_id, text)
        except errors.rpcerrorlist.UserIsBlockedError:
            await event.reply(
                "Your pm has been successfully connected to **{}**! Write to @rSophieBot \
for start using connection.".format(chat_title))
            return
        await event.reply("Your pm has been successfully connected to **{}**!".format(chat_title))


@register(incoming=True, pattern="^[/!]connect$")
async def connect(event):
    user_id = event.from_id
    if not event.chat_id == user_id:
        return
    history = mongodb.connections.find_one({'user_id': user_id})
    if not history:
        await event.reply(
            "You not connected to any chat for history, connect via `/connect <chat id>`"
        )
        return
    buttons = []
    chat_title = mongodb.chat_list.find_one({'chat_id': history['btn1']})
    buttons += [[Button.inline("{}".format(chat_title['chat_title']),
                'connect_{}'.format(history['btn1']))]]
    if history['btn2']:
        chat_title = mongodb.chat_list.find_one({'chat_id': history['btn2']})
        buttons += [[Button.inline("{}".format(chat_title['chat_title']),
                    'connect_{}'.format(history['btn2']))]]
    if history['btn3']:
        chat_title = mongodb.chat_list.find_one({'chat_id': history['btn3']})
        buttons += [[Button.inline("{}".format(chat_title['chat_title']),
                    'connect_{}'.format(history['btn3']))]]
    chat_title = mongodb.chat_list.find_one({'chat_id': int(history['chat_id'])})
    text = "**Current connected chat:**\n`"
    text += chat_title['chat_title']
    text += "`\n\n**Select chat to connect:**"
    await event.reply(text, buttons=buttons)


@register(incoming=True, pattern="^/disconnect$")
async def disconnect(event):
    user_id = event.from_id
    old = mongodb.connections.find_one({'user_id': user_id})
    if not old:
        await event.reply(
            "You was not connected to any chat before!")
        return
    chat_title = await get_conn_chat(user_id, event.chat_id)
    mongodb.connections.delete_one({'_id': old['_id']})
    redis.delete('connection_cache_{}'.format(user_id))
    await event.reply("You was desconnected from {} chat.".format(chat_title))


@bot.on(events.CallbackQuery(data=re.compile(b'connect_')))
async def event(event):
    user_id = event.original_update.user_id
    chat_id = re.search(r'connect_(.*)', str(event.data)).group(1)[:-1]
    chat_title = mongodb.chat_list.find_one({'chat_id': int(chat_id)})
    old = mongodb.connections.find_one({'user_id': user_id})
    mongodb.connections.delete_one({'_id': old['_id']})
    mongodb.connections.insert_one({
        'user_id': user_id,
        'chat_id': chat_id,
        'btn1': old['btn1'],
        'btn2': old['btn2'],
        'btn3': old['btn3'],
        'updated': old['updated']
    })
    redis.set('connection_cache_{}'.format(user_id), chat_id)
    await event.edit("Successfully connected to **{}**!".format(
        chat_title['chat_title']))


async def get_conn_chat(user_id, chat_id, admin=False):
    if not user_id == chat_id:
        chat_title = mongodb.chat_list.find_one({
            'chat_id': int(chat_id)})['chat_title']
        return True, chat_id, chat_title
    user_chats = mongodb.user_list.find_one({'user_id': user_id})['chats']
    if chat_id not in user_chats:
        return False,
        "You not in this chat anymore, i'll disconnect you.",
        None

    group_id = mongodb.connections.find_one({'user_id': int(user_id)})
    if not group_id:
        return True, user_id, "Local"
    group_id = group_id['chat_id']

    chat_title = mongodb.chat_list.find_one({
        'chat_id': int(group_id)})['chat_title']

    if admin is True:
        K = await is_user_admin(chat_id, user_id)
        if K is False:
            return False, "You should be admin in {}!".format(chat_title), None

    return True, int(group_id), chat_title
