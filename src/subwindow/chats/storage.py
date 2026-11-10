"""聊天记录 SQLite 与吧群订阅 JSON 存储。"""
import json
import os
import sqlite3
import threading
import time

import consts

from .models import ChatMessage, ChatSession


def _chat_data_dir():
    path = os.path.join(consts.datapath, 'chat_data')
    os.makedirs(path, exist_ok=True)
    return path


class ChatStore:
    """
    账号的私信记录存储
    """

    def __init__(self, uid):
        safe_uid = int(uid or 0)
        self.uid = safe_uid
        self.path = os.path.join(_chat_data_dir(), f'private_{safe_uid}.db')
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.path,
            timeout=10,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute('PRAGMA journal_mode=WAL')
            self._connection.execute('PRAGMA synchronous=NORMAL')
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS private_peers (
                    peer_user_id INTEGER PRIMARY KEY,
                    user_name TEXT NOT NULL DEFAULT '',
                    portrait TEXT NOT NULL DEFAULT '',
                    last_text TEXT NOT NULL DEFAULT '',
                    last_time INTEGER NOT NULL DEFAULT 0
                )
            """)
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS private_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL DEFAULT 0,
                    peer_user_id INTEGER NOT NULL,
                    msg_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL DEFAULT 0,
                    sender_name TEXT NOT NULL DEFAULT '',
                    sender_portrait TEXT NOT NULL DEFAULT '',
                    direction TEXT NOT NULL DEFAULT 'in',
                    msg_type INTEGER NOT NULL DEFAULT 1,
                    text TEXT NOT NULL DEFAULT '',
                    create_time INTEGER NOT NULL DEFAULT 0,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL DEFAULT '{}',
                    inserted_time REAL NOT NULL DEFAULT 0,
                    UNIQUE(peer_user_id, msg_id, direction)
                )
            """)
            columns = {
                row['name']
                for row in self._connection.execute(
                    'PRAGMA table_info(private_messages)'
                ).fetchall()
            }
            if 'group_id' not in columns:
                self._connection.execute(
                    'ALTER TABLE private_messages '
                    'ADD COLUMN group_id INTEGER NOT NULL DEFAULT 0'
                )
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS private_groups (
                    group_id INTEGER PRIMARY KEY,
                    peer_user_id INTEGER NOT NULL,
                    user_name TEXT NOT NULL DEFAULT '',
                    portrait TEXT NOT NULL DEFAULT ''
                )
            """)
            self._connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_private_messages_peer_time
                ON private_messages(peer_user_id, create_time, id)
            """)
            self._connection.commit()

    def close(self):
        with self._lock:
            self._connection.close()

    def save_message(
        self,
        peer_user_id,
        peer_name,
        peer_portrait,
        message,
        group_id=0,
    ):
        """保存消息并返回是否为新记录。"""
        peer_user_id = int(peer_user_id or 0)
        if not peer_user_id:
            return False

        payload = json.dumps(message.payload or {}, ensure_ascii=False)
        timestamp = int(message.timestamp or time.time())
        is_read = int(message.is_read or message.direction == 'out')
        with self._lock:
            cursor = self._connection.execute("""
                INSERT OR IGNORE INTO private_messages (
                    group_id, peer_user_id, msg_id, sender_id, sender_name, sender_portrait,
                    direction, msg_type, text, create_time, is_read, payload, inserted_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                int(group_id or 0),
                peer_user_id,
                int(message.message_id or 0),
                int(message.sender_id or 0),
                message.sender_name or '',
                message.sender_portrait or '',
                message.direction or 'in',
                int(message.msg_type or 0),
                message.text or '',
                timestamp,
                is_read,
                payload,
                time.time(),
            ))
            inserted = cursor.rowcount > 0

            self._connection.execute("""
                INSERT INTO private_peers (
                    peer_user_id, user_name, portrait, last_text, last_time
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(peer_user_id) DO UPDATE SET
                    user_name = CASE
                        WHEN excluded.user_name <> '' THEN excluded.user_name
                        ELSE private_peers.user_name
                    END,
                    portrait = CASE
                        WHEN excluded.portrait <> '' THEN excluded.portrait
                        ELSE private_peers.portrait
                    END,
                    last_text = CASE
                        WHEN excluded.last_time >= private_peers.last_time THEN excluded.last_text
                        ELSE private_peers.last_text
                    END,
                    last_time = MAX(private_peers.last_time, excluded.last_time)
            """, (
                peer_user_id,
                (
                    peer_name or message.sender_name
                    if message.direction == 'in'
                    else peer_name or ''
                ),
                peer_portrait or (
                    message.sender_portrait if message.direction == 'in' else ''
                ),
                message.text or '',
                timestamp,
            ))
            self._connection.commit()
        return inserted

    def set_group_peer(self, group_id, peer_user_id, user_name='', portrait=''):
        group_id = int(group_id or 0)
        peer_user_id = int(peer_user_id or 0)
        if not group_id or not peer_user_id:
            return
        with self._lock:
            self._connection.execute("""
                INSERT INTO private_groups (
                    group_id, peer_user_id, user_name, portrait
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    peer_user_id = excluded.peer_user_id,
                    user_name = CASE
                        WHEN excluded.user_name <> '' THEN excluded.user_name
                        ELSE private_groups.user_name
                    END,
                    portrait = CASE
                        WHEN excluded.portrait <> '' THEN excluded.portrait
                        ELSE private_groups.portrait
                    END
            """, (
                group_id,
                peer_user_id,
                user_name or '',
                portrait or '',
            ))
            self._connection.commit()

    def get_group_peer(self, group_id):
        with self._lock:
            row = self._connection.execute("""
                SELECT peer_user_id, user_name, portrait
                FROM private_groups
                WHERE group_id = ?
            """, (int(group_id),)).fetchone()
        if row is None:
            return None
        return {
            'peer_user_id': row['peer_user_id'],
            'user_name': row['user_name'],
            'portrait': row['portrait'],
        }

    def get_sessions(self):
        with self._lock:
            rows = self._connection.execute("""
                SELECT
                    p.peer_user_id,
                    p.user_name,
                    p.portrait,
                    p.last_text,
                    p.last_time,
                    COALESCE(SUM(CASE
                        WHEN m.direction = 'in' AND m.is_read = 0 THEN 1
                        ELSE 0
                    END), 0) AS unread_count
                FROM private_peers p
                LEFT JOIN private_messages m
                    ON m.peer_user_id = p.peer_user_id
                GROUP BY p.peer_user_id
                HAVING p.peer_user_id > 0 AND p.peer_user_id <> ?
                ORDER BY p.last_time DESC
            """, (self.uid,)).fetchall()

        return [
            ChatSession.private_session(
                row['peer_user_id'],
                row['user_name'],
                row['last_text'],
                row['portrait'],
                row['last_time'],
                row['unread_count'],
            )
            for row in rows
        ]

    def get_messages(self, peer_user_id, limit=300):
        with self._lock:
            rows = self._connection.execute("""
                SELECT * FROM (
                    SELECT *
                    FROM private_messages
                    WHERE peer_user_id = ?
                    ORDER BY create_time DESC, id DESC
                    LIMIT ?
                )
                ORDER BY create_time ASC, id ASC
            """, (int(peer_user_id), int(limit))).fetchall()

        messages = []
        for row in rows:
            messages.append(ChatMessage(
                session_key=f'private:{row["peer_user_id"]}',
                message_id=row['msg_id'],
                sender_id=row['sender_id'],
                sender_name=row['sender_name'],
                sender_portrait=row['sender_portrait'],
                direction=row['direction'],
                msg_type=row['msg_type'],
                text=row['text'],
                timestamp=row['create_time'],
                payload=json.loads(row['payload'] or '{}'),
                is_read=bool(row['is_read']),
            ))
        return messages

    def mark_read(self, peer_user_id):
        with self._lock:
            self._connection.execute("""
                UPDATE private_messages
                SET is_read = 1
                WHERE peer_user_id = ? AND direction = 'in'
            """, (int(peer_user_id),))
            self._connection.commit()

    def total_unread(self):
        with self._lock:
            row = self._connection.execute("""
                SELECT COUNT(*) AS count
                FROM private_messages
                WHERE direction = 'in' AND is_read = 0
            """).fetchone()
        return int(row['count'] if row else 0)


class ChatRoomSubscriptionStore:
    """当前账号订阅的吧群列表。"""

    def __init__(self, uid):
        self.uid = int(uid or 0)
        self.path = os.path.join(_chat_data_dir(), f'chatrooms_{self.uid}.json')
        self._lock = threading.RLock()
        self._rooms = {}
        self._load()

    def _load(self):
        with self._lock:
            if not os.path.isfile(self.path):
                self._rooms = {}
                return
            try:
                with open(self.path, 'rt', encoding='utf-8') as file:
                    data = json.load(file)
            except (OSError, ValueError):
                data = {}
            self._rooms = {
                str(item.get('room_id')): item
                for item in data.get('rooms', [])
                if item.get('room_id')
            }

    def _save(self):
        with open(self.path, 'wt', encoding='utf-8') as file:
            json.dump(
                {'rooms': list(self._rooms.values())},
                file,
                ensure_ascii=False,
                indent=2,
            )

    def list_rooms(self):
        with self._lock:
            rooms = [dict(item) for item in self._rooms.values()]
        rooms.sort(key=lambda item: int(item.get('last_time', 0) or 0), reverse=True)
        return rooms

    def add_room(self, room):
        room_id = int(room.get('room_id') or room.get('id') or 0)
        if not room_id:
            return None
        with self._lock:
            old = self._rooms.get(str(room_id), {})
            item = dict(old)
            item.update(room)
            item['room_id'] = room_id
            self._rooms[str(room_id)] = item
            self._save()
            return dict(item)

    def update_room(self, room_id, **changes):
        with self._lock:
            item = self._rooms.get(str(int(room_id)))
            if item is None:
                return None
            item.update(changes)
            self._save()
            return dict(item)

    def remove_room(self, room_id):
        with self._lock:
            self._rooms.pop(str(int(room_id)), None)
            self._save()
