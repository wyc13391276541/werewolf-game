import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify, make_response
from flask_socketio import SocketIO, emit, join_room, leave_room
import random
import time
from datetime import datetime
import threading
import uuid
import sys
import logging

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# ============================================
# 多语言支持 / Multi-language Support
# ============================================
LANG = 'zh'  # 'zh' for Chinese, 'en' for English

def t(zh_text, en_text):
    """翻译辅助函数 / Translation helper"""
    return en_text if LANG == 'en' else zh_text

# ============================================
# 消息字典 / Message Dictionary
# ============================================
MSG = {
    'room_closed': t('房间已关闭', 'Room closed'),
    'server_full': t('服务器房间已满，请稍后再试', 'Server is full, please try again later'),
    'enter_name': t('请输入昵称', 'Please enter a nickname'),
    'room_not_exist': t('房间不存在', 'Room does not exist'),
    'game_ended': t('游戏已结束', 'Game has ended'),
    'room_not_open': t('房间暂未开放', 'Room is not open yet'),
    'invalid_room_code': t('无效的房间号', 'Invalid room code'),
    'game_started_cannot_join': t('游戏已开始，无法加入', 'Game has started, cannot join'),
    'name_taken': t('昵称已被使用', 'Nickname is already taken'),
    'room_full': t('房间已满', 'Room is full'),
    'cannot_modify': t('房间已开放，无法修改', 'Room is open, cannot modify'),
    'no_online_players': t('没有在线玩家', 'No online players'),
    'auth_failed': t('身份验证失败', 'Authentication failed'),
    'room_code_invalid': t('房间号和昵称不能为空', 'Room code and nickname are required'),
    'god_ended_game': t('上帝结束了游戏', 'God has ended the game'),
    'game_reset': t('游戏已重置', 'Game has been reset'),
    'page_not_found': t('页面不存在', 'Page not found'),
}

# ============================================
# 应用配置 / App Configuration
# ============================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'werewolf'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 86400

socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='eventlet', 
    ping_timeout=60, 
    ping_interval=25,
    logger=False,
    engineio_logger=False
)

# ============================================
# 游戏数据 / Game Data
# ============================================
rooms = {}
MAX_ROOMS = 15
ROOM_TIMEOUT = 35 * 60
GOD_OFFLINE_TOLERANCE = 3 * 60
ws_rooms = {}
user_rooms = {}

# 角色列表 / Role List (Bilingual)
AVAILABLE_ROLES = [
    '狼人 / Werewolf', 
    '预言家 / Seer', 
    '女巫 / Witch', 
    '猎人 / Hunter', 
    '守卫 / Guard', 
    '白痴 / Idiot', 
    '平民 / Villager',
    '白狼王 / White Wolf King', 
    '狼美人 / Wolf Beauty', 
    '石像鬼 / Gargoyle', 
    '丘比特 / Cupid', 
    '长老 / Elder', 
    '替罪羊 / Scapegoat', 
    '吹笛者 / Pied Piper'
]

# 默认角色配置 / Default Role Configurations
DEFAULT_ROLES = {
    4: ['狼人 / Werewolf', '预言家 / Seer', '女巫 / Witch', '平民 / Villager'],
    5: ['狼人 / Werewolf', '狼人 / Werewolf', '预言家 / Seer', '女巫 / Witch', '平民 / Villager'],
    6: ['狼人 / Werewolf', '狼人 / Werewolf', '预言家 / Seer', '女巫 / Witch', '猎人 / Hunter', '平民 / Villager'],
    7: ['狼人 / Werewolf', '狼人 / Werewolf', '狼人 / Werewolf', '预言家 / Seer', '女巫 / Witch', '猎人 / Hunter', '平民 / Villager'],
    8: ['狼人 / Werewolf', '狼人 / Werewolf', '狼人 / Werewolf', '预言家 / Seer', '女巫 / Witch', '猎人 / Hunter', '守卫 / Guard', '平民 / Villager'],
    9: ['狼人 / Werewolf', '狼人 / Werewolf', '狼人 / Werewolf', '预言家 / Seer', '女巫 / Witch', '猎人 / Hunter', '守卫 / Guard', '平民 / Villager', '平民 / Villager'],
    10: ['狼人 / Werewolf', '狼人 / Werewolf', '狼人 / Werewolf', '狼人 / Werewolf', '预言家 / Seer', '女巫 / Witch', '猎人 / Hunter', '守卫 / Guard', '平民 / Villager', '平民 / Villager'],
    11: ['狼人 / Werewolf', '狼人 / Werewolf', '狼人 / Werewolf', '狼人 / Werewolf', '预言家 / Seer', '女巫 / Witch', '猎人 / Hunter', '守卫 / Guard', '白痴 / Idiot', '平民 / Villager', '平民 / Villager'],
    12: ['狼人 / Werewolf', '狼人 / Werewolf', '狼人 / Werewolf', '狼人 / Werewolf', '预言家 / Seer', '女巫 / Witch', '猎人 / Hunter', '守卫 / Guard', '白痴 / Idiot', '平民 / Villager', '平民 / Villager', '平民 / Villager']
}

# ============================================
# 辅助函数 / Helper Functions
# ============================================
def generate_room_code():
    """生成6位房间码 / Generate 6-digit room code"""
    return ''.join([str(random.randint(0, 9)) for _ in range(6)])

def cleanup_expired_rooms():
    """清理过期房间 / Clean up expired rooms"""
    current_time = time.time()
    expired_rooms = []
    
    for room_id, room_data in list(rooms.items()):
        created_at = room_data.get('created_at')
        if created_at and current_time - created_at > ROOM_TIMEOUT:
            expired_rooms.append(room_id)
            continue
        
        god_offline_since = room_data.get('god_offline_since')
        if god_offline_since and current_time - god_offline_since > GOD_OFFLINE_TOLERANCE:
            expired_rooms.append(room_id)
    
    for room_id in expired_rooms:
        room_code = rooms[room_id]['code']
        socketio.emit('room_closed', {'message': MSG['room_closed']}, to=room_code)
        
        for uid, info in list(user_rooms.items()):
            if info['room_code'] == room_code:
                del user_rooms[uid]
        
        del rooms[room_id]

def cleanup_thread():
    """清理线程 / Cleanup thread"""
    while True:
        time.sleep(30)
        cleanup_expired_rooms()

threading.Thread(target=cleanup_thread, daemon=True).start()

def check_auto_start(room_id):
    """检查是否自动开始 / Check auto-start condition"""
    if room_id not in rooms:
        return
    
    room_data = rooms[room_id]
    if room_data.get('game_started') or not room_data.get('accepting_players', False):
        return
    
    online_players = [p for p, info in room_data['players'].items() if info.get('online', False)]
    if len(online_players) == room_data['max_players']:
        room_data['accepting_players'] = False
        start_game_internal(room_id)

def start_game_internal(room_id):
    """内部开始游戏函数 / Internal start game function"""
    room_data = rooms[room_id]
    online_players = [p for p, info in room_data['players'].items() if info.get('online', False)]
    roles = room_data['role_config'].copy()
    
    if len(roles) != len(online_players):
        if len(roles) < len(online_players):
            roles.extend(['平民 / Villager'] * (len(online_players) - len(roles)))
        else:
            roles = roles[:len(online_players)]
        room_data['role_config'] = roles
    
    random.shuffle(roles)
    
    assigned = {}
    for i, player in enumerate(online_players):
        assigned[player] = roles[i]
    
    room_data['assigned_roles'] = assigned
    room_data['game_started'] = True
    
    god_sid = room_data.get('god_sid')
    if god_sid:
        socketio.emit('god_view', {'all_roles': assigned, 'players': online_players}, to=god_sid)
    
    for player, role in assigned.items():
        player_info = room_data['players'].get(player)
        if player_info and player_info.get('online'):
            player_sid = player_info.get('sid')
            if player_sid:
                socketio.emit('role_assigned', {'role': role}, to=player_sid)
    
    socketio.emit('game_started', {'players': online_players}, to=room_data['code'])

def get_created_str(room_data):
    """获取创建时间字符串 / Get creation time string"""
    created_at = room_data.get('created_at', time.time())
    if isinstance(created_at, (int, float)):
        return datetime.fromtimestamp(created_at).strftime('%Y-%m-%d %H:%M:%S')
    return str(created_at)

# ============================================
# Socket.IO 事件处理 / Socket.IO Event Handlers
# ============================================
@socketio.on('connect')
def handle_connect():
    """处理客户端连接 / Handle client connection"""
    user_id = request.args.get('user_id')
    
    if user_id and user_id in user_rooms:
        room_info = user_rooms[user_id]
        room_code = room_info['room_code']
        player_name = room_info['player_name']
        is_god = room_info['is_god']
        
        for room_id, room_data in rooms.items():
            if room_data['code'] == room_code:
                if is_god:
                    room_data['god_sid'] = request.sid
                    room_data['god_offline_since'] = None
                    
                    ws_rooms[request.sid] = {
                        'room_code': room_code,
                        'player_name': player_name,
                        'room_id': room_id,
                        'is_god': True,
                        'user_id': user_id
                    }
                    
                    join_room(room_code)
                    socketio.emit('god_status', {'online': True, 'god_name': player_name}, to=room_code)
                    
                    if room_data.get('game_started'):
                        assigned_roles = room_data.get('assigned_roles', {})
                        players_list = list(room_data['players'].keys())
                        
                        emit('god_view', {
                            'all_roles': assigned_roles,
                            'players': players_list
                        })
                        
                        emit('god_reconnected', {
                            'game_started': True,
                            'accepting_players': False,
                            'players': players_list,
                            'all_roles': assigned_roles
                        })
                        
                        socketio.emit('players_updated', {
                            'players': players_list,
                            'player_count': len(players_list),
                            'max_players': room_data['max_players']
                        }, to=room_code)
                    else:
                        emit('god_reconnected', {
                            'accepting_players': room_data.get('accepting_players', False),
                            'players': list(room_data['players'].keys()),
                            'max_players': room_data['max_players'],
                            'role_config': room_data['role_config'],
                            'available_roles': AVAILABLE_ROLES,
                            'created_at': get_created_str(room_data),
                            'game_started': False
                        })
                    
                elif player_name in room_data['players']:
                    player_info = room_data['players'][player_name]
                    if player_info.get('user_id') == user_id:
                        player_info['sid'] = request.sid
                        player_info['online'] = True
                        
                        ws_rooms[request.sid] = {
                            'room_code': room_code,
                            'player_name': player_name,
                            'room_id': room_id,
                            'is_god': False,
                            'user_id': user_id
                        }
                        
                        join_room(room_code)
                        socketio.emit('player_online', {'player_name': player_name}, to=room_code)
                        
                        my_role = room_data['assigned_roles'].get(player_name) if room_data.get('game_started') else None
                        emit('player_reconnected', {
                            'game_started': room_data.get('game_started', False),
                            'players': list(room_data['players'].keys()),
                            'max_players': room_data['max_players'],
                            'god_name': room_data['god_name'],
                            'my_role': my_role
                        })
                    else:
                        emit('error', {'message': MSG['auth_failed']})
                        return
                
                socketio.emit('players_updated', {
                    'players': list(room_data['players'].keys()),
                    'player_count': len(room_data['players']),
                    'max_players': room_data['max_players']
                }, to=room_code)
                return

@socketio.on('disconnect')
def handle_disconnect():
    """处理客户端断开连接 / Handle client disconnection"""
    if request.sid in ws_rooms:
        room_info = ws_rooms[request.sid]
        room_code = room_info['room_code']
        player_name = room_info.get('player_name')
        is_god = room_info.get('is_god', False)
        
        for room_id, room_data in list(rooms.items()):
            if room_data['code'] == room_code:
                if is_god:
                    room_data['god_offline_since'] = time.time()
                    room_data['god_sid'] = None
                    socketio.emit('god_status', {'online': False, 'god_name': player_name}, to=room_code)
                elif player_name and player_name in room_data.get('players', {}):
                    player_info = room_data['players'][player_name]
                    player_info['online'] = False
                    player_info['sid'] = None
                    socketio.emit('player_offline', {'player_name': player_name}, to=room_code)
                break
        
        leave_room(room_code)
        del ws_rooms[request.sid]

@socketio.on('create_room')
def handle_create_room(data):
    """处理创建房间请求 / Handle create room request"""
    if len(rooms) >= MAX_ROOMS:
        emit('error', {'message': MSG['server_full']})
        return
    
    player_name = data.get('player_name', '').strip()
    if not player_name:
        emit('error', {'message': MSG['enter_name']})
        return
    
    user_id = data.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
    
    if user_id in user_rooms:
        room_info = user_rooms[user_id]
        room_code = room_info['room_code']
        
        for room_id, room_data in rooms.items():
            if room_data['code'] == room_code:
                if not room_data.get('game_ended', False) and room_info['is_god']:
                    room_data['god_sid'] = request.sid
                    room_data['god_offline_since'] = None
                    
                    ws_rooms[request.sid] = {
                        'room_code': room_code,
                        'player_name': player_name,
                        'room_id': room_id,
                        'is_god': True,
                        'user_id': user_id
                    }
                    join_room(room_code)
                    
                    emit('god_reconnected', {
                        'accepting_players': room_data.get('accepting_players', False),
                        'players': list(room_data['players'].keys()),
                        'max_players': room_data['max_players'],
                        'role_config': room_data['role_config'],
                        'available_roles': AVAILABLE_ROLES,
                        'created_at': get_created_str(room_data),
                        'game_started': room_data.get('game_started', False)
                    })
                    return
                break
        
        del user_rooms[user_id]
    
    room_code = generate_room_code()
    while any(r['code'] == room_code for r in rooms.values()):
        room_code = generate_room_code()
    
    room_id = str(int(time.time() * 1000))
    
    rooms[room_id] = {
        'code': room_code,
        'players': {},
        'god_name': player_name,
        'god_sid': request.sid,
        'god_offline_since': None,
        'game_started': False,
        'game_ended': False,
        'accepting_players': False,
        'assigned_roles': {},
        'max_players': 6,
        'role_config': DEFAULT_ROLES[6].copy(),
        'created_at': time.time(),
        'user_id': user_id
    }
    
    user_rooms[user_id] = {
        'room_code': room_code,
        'player_name': player_name,
        'is_god': True
    }
    
    join_room(room_code)
    ws_rooms[request.sid] = {
        'room_code': room_code,
        'player_name': player_name,
        'room_id': room_id,
        'is_god': True,
        'user_id': user_id
    }
    
    emit('room_created', {
        'success': True,
        'room_code': room_code,
        'god_name': player_name,
        'max_players': 6,
        'role_config': rooms[room_id]['role_config'],
        'available_roles': AVAILABLE_ROLES,
        'created_at': get_created_str(rooms[room_id]),
        'user_id': user_id
    })

@socketio.on('join_room')
def handle_join_room(data):
    """处理加入房间请求 / Handle join room request"""
    room_code = data.get('room_code', '').strip()
    player_name = data.get('player_name', '').strip()
    user_id = data.get('user_id')
    
    if not room_code or not player_name:
        emit('error', {'message': MSG['room_code_invalid']})
        return
    
    if room_code == 'new':
        emit('error', {'message': MSG['invalid_room_code']})
        return
    
    room_id = None
    room_data = None
    for rid, rdata in rooms.items():
        if rdata['code'] == room_code:
            room_id = rid
            room_data = rdata
            break
    
    if not room_id:
        emit('error', {'message': MSG['room_not_exist']})
        return
    
    if room_data.get('game_ended', False):
        emit('error', {'message': MSG['game_ended']})
        return
    
    if not room_data.get('accepting_players', False) and not room_data.get('game_started', False):
        emit('error', {'message': MSG['room_not_open']})
        return
    
    if not user_id:
        user_id = str(uuid.uuid4())
    
    is_same = False
    if user_id in user_rooms:
        info = user_rooms[user_id]
        if info['room_code'] == room_code and info['player_name'] == player_name:
            is_same = True
    
    if is_same:
        if player_name in room_data['players']:
            player_info = room_data['players'][player_name]
            player_info['sid'] = request.sid
            player_info['online'] = True
    else:
        if room_data['game_started']:
            if player_name not in room_data['players']:
                emit('error', {'message': MSG['game_started_cannot_join']})
                return
        
        if player_name in room_data['players']:
            existing_info = room_data['players'][player_name]
            if existing_info.get('online', False) and existing_info.get('user_id') != user_id:
                emit('error', {'message': MSG['name_taken']})
                return
        
        online_count = sum(1 for p in room_data['players'].values() if p.get('online', False))
        if online_count >= room_data['max_players'] and player_name not in room_data['players']:
            emit('error', {'message': MSG['room_full']})
            return
        
        room_data['players'][player_name] = {
            'sid': request.sid,
            'online': True,
            'user_id': user_id
        }
        
        user_rooms[user_id] = {
            'room_code': room_code,
            'player_name': player_name,
            'is_god': False
        }
    
    join_room(room_code)
    
    ws_rooms[request.sid] = {
        'room_code': room_code,
        'player_name': player_name,
        'room_id': room_id,
        'is_god': False,
        'user_id': user_id
    }
    
    my_role = room_data['assigned_roles'].get(player_name) if room_data.get('game_started') else None
    
    emit('room_joined', {
        'success': True,
        'room_code': room_code,
        'player_name': player_name,
        'players': list(room_data['players'].keys()),
        'max_players': room_data['max_players'],
        'god_name': room_data['god_name'],
        'user_id': user_id,
        'game_started': room_data.get('game_started', False),
        'my_role': my_role
    })
    
    socketio.emit('players_updated', {
        'players': list(room_data['players'].keys()),
        'player_count': len(room_data['players']),
        'max_players': room_data['max_players']
    }, to=room_code)
    
    if not is_same and not room_data.get('game_started'):
        god_sid = room_data.get('god_sid')
        if god_sid:
            socketio.emit('player_joined', {'player_name': player_name}, to=god_sid)
        check_auto_start(room_id)

@socketio.on('open_room')
def handle_open_room(data):
    """处理开放房间请求 / Handle open room request"""
    room_code = data.get('room_code')
    for room_id, room_data in rooms.items():
        if room_data['code'] == room_code and room_data['god_sid'] == request.sid:
            room_data['accepting_players'] = True
            socketio.emit('room_opened', {
                'message': t('房间已开放', 'Room is now open'),
                'max_players': room_data['max_players']
            }, to=room_code)
            break

@socketio.on('end_game')
def handle_end_game(data):
    """处理结束游戏请求 / Handle end game request"""
    room_code = data.get('room_code')
    for room_id, room_data in rooms.items():
        if room_data['code'] == room_code and room_data['god_sid'] == request.sid:
            room_data['game_started'] = False
            room_data['game_ended'] = True
            room_data['accepting_players'] = False
            room_data['assigned_roles'] = {}
            
            for uid, info in list(user_rooms.items()):
                if info['room_code'] == room_code:
                    del user_rooms[uid]
            
            socketio.emit('game_ended', {'message': MSG['god_ended_game']}, to=room_code)
            break

@socketio.on('update_settings')
def handle_update_settings(data):
    """处理更新设置请求 / Handle update settings request"""
    room_code = data.get('room_code')
    max_players = data.get('max_players', 6)
    
    for room_id, room_data in rooms.items():
        if room_data['code'] == room_code and room_data['god_sid'] == request.sid:
            if room_data['accepting_players']:
                emit('error', {'message': MSG['cannot_modify']})
                return
            
            room_data['max_players'] = max_players
            if max_players in DEFAULT_ROLES:
                room_data['role_config'] = DEFAULT_ROLES[max_players].copy()
            else:
                wolf_count = max(1, max_players // 3)
                room_data['role_config'] = ['狼人 / Werewolf'] * wolf_count + ['预言家 / Seer', '女巫 / Witch']
                remaining = max_players - len(room_data['role_config'])
                if remaining > 0:
                    room_data['role_config'].extend(['平民 / Villager'] * remaining)
            
            socketio.emit('settings_updated', {
                'max_players': max_players,
                'role_config': room_data['role_config']
            }, to=room_code)
            break

@socketio.on('add_role')
def handle_add_role(data):
    """处理添加角色请求 / Handle add role request"""
    room_code = data.get('room_code')
    role = data.get('role')
    
    for room_id, room_data in rooms.items():
        if room_data['code'] == room_code and room_data['god_sid'] == request.sid:
            if room_data['accepting_players']:
                emit('error', {'message': MSG['cannot_modify']})
                return
            room_data['role_config'].append(role)
            room_data['max_players'] = len(room_data['role_config'])
            socketio.emit('settings_updated', {
                'max_players': room_data['max_players'],
                'role_config': room_data['role_config']
            }, to=room_code)
            break

@socketio.on('remove_role')
def handle_remove_role(data):
    """处理移除角色请求 / Handle remove role request"""
    room_code = data.get('room_code')
    index = data.get('index')
    
    for room_id, room_data in rooms.items():
        if room_data['code'] == room_code and room_data['god_sid'] == request.sid:
            if room_data['accepting_players']:
                emit('error', {'message': MSG['cannot_modify']})
                return
            if 0 <= index < len(room_data['role_config']):
                room_data['role_config'].pop(index)
                room_data['max_players'] = len(room_data['role_config'])
            socketio.emit('settings_updated', {
                'max_players': room_data['max_players'],
                'role_config': room_data['role_config']
            }, to=room_code)
            break

@socketio.on('start_game_manual')
def handle_start_game_manual(data):
    """处理手动开始游戏请求 / Handle manual start game request"""
    room_code = data.get('room_code')
    for room_id, room_data in rooms.items():
        if room_data['code'] == room_code and room_data['god_sid'] == request.sid:
            online_players = [p for p, info in room_data['players'].items() if info.get('online', False)]
            if len(online_players) == 0:
                emit('error', {'message': MSG['no_online_players']})
                return
            
            if len(room_data['role_config']) != len(online_players):
                roles = room_data['role_config'].copy()
                if len(roles) < len(online_players):
                    roles.extend(['平民 / Villager'] * (len(online_players) - len(roles)))
                else:
                    roles = roles[:len(online_players)]
                room_data['role_config'] = roles
                room_data['max_players'] = len(online_players)
            
            room_data['accepting_players'] = False
            start_game_internal(room_id)
            break

@socketio.on('reveal_role')
def handle_reveal_role(data):
    """处理揭示角色请求 / Handle reveal role request"""
    room_code = data.get('room_code')
    player_name = data.get('player_name')
    
    for room_id, room_data in rooms.items():
        if room_data['code'] == room_code and room_data['god_sid'] == request.sid:
            if player_name in room_data['assigned_roles']:
                socketio.emit('role_revealed', {
                    'player': player_name,
                    'role': room_data['assigned_roles'][player_name]
                }, to=room_code)
            break

@socketio.on('reset_game')
def handle_reset_game(data):
    """处理重置游戏请求 / Handle reset game request"""
    room_code = data.get('room_code')
    for room_id, room_data in rooms.items():
        if room_data['code'] == room_code and room_data['god_sid'] == request.sid:
            room_data['game_started'] = False
            room_data['accepting_players'] = False
            room_data['assigned_roles'] = {}
            socketio.emit('game_reset', {
                'players': list(room_data['players'].keys()),
                'message': MSG['game_reset']
            }, to=room_code)
            break

@socketio.on('kick_player')
def handle_kick_player(data):
    """处理踢出玩家请求 / Handle kick player request"""
    room_code = data.get('room_code')
    player_name = data.get('player_name')
    
    for room_id, room_data in rooms.items():
        if room_data['code'] == room_code and room_data['god_sid'] == request.sid:
            if player_name in room_data['players']:
                player_info = room_data['players'][player_name]
                user_id = player_info.get('user_id')
                player_sid = player_info.get('sid')
                
                del room_data['players'][player_name]
                
                if user_id and user_id in user_rooms:
                    del user_rooms[user_id]
                
                if player_sid:
                    socketio.emit('you_were_kicked', {}, to=player_sid)
                
                socketio.emit('players_updated', {
                    'players': list(room_data['players'].keys()),
                    'player_count': len(room_data['players']),
                    'max_players': room_data['max_players']
                }, to=room_code)
            break

# ============================================
# HTTP 路由 / HTTP Routes
# ============================================
@app.route('/')
def index():
    """首页 / Home page"""
    return make_response(render_template('index.html', max_rooms=MAX_ROOMS))

@app.route('/room/<room_code>')
def room(room_code):
    """房间页 / Room page"""
    return make_response(render_template('room.html', room_code=room_code))

@app.route('/api/check_room/<room_code>')
def check_room(room_code):
    """检查房间状态 / Check room status"""
    for room_data in rooms.values():
        if room_data['code'] == room_code:
            online_count = sum(1 for p in room_data['players'].values() if p.get('online', False))
            return jsonify({
                'exists': True,
                'accepting': room_data.get('accepting_players', False),
                'player_count': online_count,
                'max_players': room_data['max_players'],
                'game_started': room_data['game_started'],
                'god_name': room_data['god_name'],
                'god_online': room_data.get('god_sid') is not None
            })
    return jsonify({'exists': False})

@app.route('/api/check_user_room/<user_id>')
def check_user_room(user_id):
    """检查用户所在房间 / Check user's room"""
    if user_id in user_rooms:
        room_info = user_rooms[user_id]
        room_code = room_info['room_code']
        for room_data in rooms.values():
            if room_data['code'] == room_code and not room_data.get('game_ended', False):
                return jsonify({
                    'has_room': True,
                    'room_code': room_code,
                    'is_god': room_info['is_god'],
                    'game_started': room_data['game_started'],
                    'god_online': room_data.get('god_sid') is not None
                })
    return jsonify({'has_room': False})

@app.route('/api/available_roles')
def available_roles():
    """获取可用角色列表 / Get available roles"""
    return jsonify({'roles': AVAILABLE_ROLES})

@app.route('/api/room_count')
def room_count():
    """获取房间数量 / Get room count"""
    return jsonify({'current': len(rooms), 'max': MAX_ROOMS})

@app.errorhandler(404)
def not_found(error):
    """404错误处理 / 404 error handler"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found', 'exists': False, 'has_room': False}), 404
    return render_template('error.html', message=MSG['page_not_found']), 404

# ============================================
# 启动应用 / Start Application
# ============================================
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)