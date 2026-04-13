import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() => runApp(const MesangeApp());

class MesangeApp extends StatelessWidget {
  const MesangeApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Mesange',
      theme: ThemeData.dark().copyWith(
        primaryColor: const Color(0xFF00d9ff),
        scaffoldBackgroundColor: const Color(0xFF1a1a2e),
      ),
      home: const AuthScreen(),
    );
  }
}

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool isRegister = false;
  String? error;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Container(
          padding: const EdgeInsets.all(30),
          margin: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.1),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Mesange', style: TextStyle(fontSize: 32, color: Color(0xFF00d9ff))),
              const SizedBox(height: 30),
              TextField(
                controller: _usernameController,
                decoration: const InputDecoration(
                  labelText: 'Логин',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 15),
              TextField(
                controller: _passwordController,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Пароль',
                  border: OutlineInputBorder(),
                ),
              ),
              if (error != null) Padding(
                padding: const EdgeInsets.only(top: 10),
                child: Text(error!, style: const TextStyle(color: Colors.red)),
              ),
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: _handleAuth,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF00d9ff),
                  minimumSize: const Size(double.infinity, 50),
                ),
                child: Text(isRegister ? 'Регистрация' : 'Вход'),
              ),
              TextButton(
                onPressed: () => setState(() => isRegister = !isRegister),
                child: Text(isRegister ? 'Есть аккаунт? Вход' : 'Нет аккаунта? Регистрация'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _handleAuth() async {
    final username = _usernameController.text.trim();
    final password = _passwordController.text;
    if (username.isEmpty || password.isEmpty) {
      setState(() => error = 'Заполните все поля');
      return;
    }

    try {
      final endpoint = isRegister ? '/api/register' : '/api/login';
      final response = await http.post(
        Uri.parse('${AppConfig.serverUrl}$endpoint'),
        body: {'username': username, 'password': password},
      );
      final data = jsonDecode(response.body);

      if (data['success']) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('username', username);
        await prefs.setInt('user_id', data['user_id']);
        await prefs.setBool('is_admin', data['is_admin'] ?? false);

        if (mounted) {
          Navigator.pushReplacement(
            context,
            MaterialPageRoute(builder: (_) => HomeScreen(username: username)),
          );
        }
      } else {
        setState(() => error = data['error']);
      }
    } catch (e) {
      setState(() => error = 'Ошибка соединения');
    }
  }
}

class HomeScreen extends StatefulWidget {
  final String username;
  const HomeScreen({super.key, required this.username});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Привет, ${widget.username}'),
        backgroundColor: const Color(0xFF16213e),
      ),
      body: [_RoomsTab(username: widget.username), DMTab(username: widget.username)][_currentIndex],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (i) => setState(() => _currentIndex = i),
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.chat), label: 'Чаты'),
          BottomNavigationBarItem(icon: Icon(Icons.message), label: 'ЛС'),
        ],
      ),
    );
  }
}

class _RoomsTab extends StatefulWidget {
  final String username;
  const _RoomsTab({required this.username});

  @override
  State<_RoomsTab> createState() => _RoomsTabState();
}

class _RoomsTabState extends State<_RoomsTab> {
  List<dynamic> rooms = [];

  @override
  void initState() {
    super.initState();
    loadRooms();
  }

  Future<void> loadRooms() async {
    try {
      final response = await http.get(Uri.parse('${AppConfig.serverUrl}/api/rooms'));
      setState(() => rooms = jsonDecode(response.body));
    } catch (e) {
      // ignore
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: rooms.length,
      itemBuilder: (context, index) {
        final room = rooms[index];
        return ListTile(
          leading: Icon(room['is_private'] ? Icons.lock : Icons.tag, color: const Color(0xFF00d9ff)),
          title: Text('#${room["name"]}'),
          subtitle: Text(room['description'] ?? ''),
          onTap: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => ChatScreen(room: room, username: widget.username),
            ),
          ),
        );
      },
    );
  }
}

class DMTab extends StatefulWidget {
  final String username;
  const DMTab({required this.username});

  @override
  State<DMTab> createState() => _DMTabState();
}

class _DMTabState extends State<DMTab> {
  List<dynamic> conversations = [];

  @override
  void initState() {
    super.initState();
    loadConversations();
  }

  Future<void> loadConversations() async {
    try {
      final response = await http.get(
        Uri.parse('${AppConfig.serverUrl}/api/dm?username=${widget.username}'),
      );
      setState(() => conversations = jsonDecode(response.body));
    } catch (e) {
      // ignore
    }
  }

  @override
  Widget build(BuildContext context) {
    if (conversations.isEmpty) {
      return const Center(child: Text('Нет диалогов', style: TextStyle(color: Colors.grey)));
    }
    return ListView.builder(
      itemCount: conversations.length,
      itemBuilder: (context, index) {
        final conv = conversations[index];
        return ListTile(
          leading: CircleAvatar(
            backgroundColor: const Color(0xFF00d9ff),
            child: Text(conv['username'][0].toUpperCase()),
          ),
          title: Row(
            children: [
              Text(conv['username']),
              const SizedBox(width: 8),
              Icon(
                conv['is_online'] ? Icons.circle : Icons.circle_outlined,
                size: 12,
                color: conv['is_online'] ? Colors.green : Colors.grey,
              ),
            ],
          ),
          subtitle: Text(conv['last_message'] ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
          trailing: conv['unread_count'] > 0
              ? Container(
                  padding: const EdgeInsets.all(6),
                  decoration: const BoxDecoration(
                    color: Colors.red,
                    shape: BoxShape.circle,
                  ),
                  child: Text('${conv['unread_count']}', style: const TextStyle(color: Colors.white, fontSize: 12)),
                )
              : null,
          onTap: () => Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => DMChatScreen(
                otherUserId: conv['user_id'],
                otherUsername: conv['username'],
                username: widget.username,
              ),
            ),
          ),
        );
      },
    );
  }
}

class ChatScreen extends StatefulWidget {
  final Map<String, dynamic> room;
  final String username;
  const ChatScreen({super.key, required this.room, required this.username});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _messageController = TextEditingController();
  List<dynamic> messages = [];
  WebSocketChannel? ws;

  @override
  void initState() {
    super.initState();
    loadMessages();
    _connectWebSocket();
  }

  Future<void> loadMessages() async {
    final response = await http.get(
      Uri.parse('${AppConfig.serverUrl}/api/messages/${widget.room["id"]}'),
    );
    setState(() => messages = jsonDecode(response.body));
  }

  void _connectWebSocket() {
    try {
      ws = WebSocketChannel.connect(Uri.parse(AppConfig.wsUrl));
      ws!.sink.add(jsonEncode({
        'action': 'join_room',
        'room_id': widget.room['id'],
        'username': widget.username,
      }));
      ws!.stream.listen((data) {
        final msg = jsonDecode(data);
        if (msg['type'] == 'message') {
          setState(() => messages.add(msg));
        }
      });
    } catch (e) {
      // ignore
    }
  }

  void _sendMessage() {
    final content = _messageController.text.trim();
    if (content.isEmpty || ws == null) return;
    ws!.sink.add(jsonEncode({'action': 'message', 'content': content}));
    _messageController.clear();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('#${widget.room["name"]}'),
        backgroundColor: const Color(0xFF16213e),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              itemCount: messages.length,
              itemBuilder: (context, index) {
                final msg = messages[index];
                final isOwn = msg['username'] == widget.username;
                return Align(
                  alignment: isOwn ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.all(8),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: isOwn ? const Color(0xFF00d9ff) : Colors.white.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (!isOwn)
                          Text(msg['username'], style: const TextStyle(color: Color(0xFF00d9ff), fontSize: 12)),
                        Text(msg['content'], style: TextStyle(color: isOwn ? Colors.black : Colors.white)),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _messageController,
                    decoration: InputDecoration(
                      hintText: 'Сообщение...',
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(24)),
                      filled: true,
                      fillColor: Colors.white.withOpacity(0.1),
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.send, color: Color(0xFF00d9ff)),
                  onPressed: _sendMessage,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    ws?.sink.close();
    super.dispose();
  }
}

class DMChatScreen extends StatefulWidget {
  final int otherUserId;
  final String otherUsername;
  final String username;
  const DMChatScreen({
    super.key,
    required this.otherUserId,
    required this.otherUsername,
    required this.username,
  });

  @override
  State<DMChatScreen> createState() => _DMChatScreenState();
}

class _DMChatScreenState extends State<DMChatScreen> {
  final _messageController = TextEditingController();
  List<dynamic> messages = [];

  @override
  void initState() {
    super.initState();
    loadMessages();
  }

  Future<void> loadMessages() async {
    final response = await http.get(
      Uri.parse('${AppConfig.serverUrl}/api/dm/${widget.otherUserId}?username=${widget.username}'),
    );
    setState(() => messages = jsonDecode(response.body));
  }

  Future<void> _sendMessage() async {
    final content = _messageController.text.trim();
    if (content.isEmpty) return;

    await http.post(
      Uri.parse('${AppConfig.serverUrl}/api/dm?username=${widget.username}'),
      body: {'receiver': widget.otherUsername, 'content': content},
    );
    _messageController.clear();
    loadMessages();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('ЛС: ${widget.otherUsername}'),
        backgroundColor: const Color(0xFF16213e),
        actions: [
          IconButton(
            icon: const Icon(Icons.videocam),
            onPressed: () {
              // Video call - TODO: implement WebRTC
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Видеозвонок скоро!')),
              );
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              itemCount: messages.length,
              itemBuilder: (context, index) {
                final msg = messages[index];
                final isOwn = msg['is_mine'];
                return Align(
                  alignment: isOwn ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.all(8),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: isOwn ? const Color(0xFF00d9ff) : Colors.white.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Text(msg['content'], style: TextStyle(color: isOwn ? Colors.black : Colors.white)),
                  ),
                );
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _messageController,
                    decoration: InputDecoration(
                      hintText: 'Сообщение...',
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(24)),
                      filled: true,
                      fillColor: Colors.white.withOpacity(0.1),
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.send, color: Color(0xFF00d9ff)),
                  onPressed: _sendMessage,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
