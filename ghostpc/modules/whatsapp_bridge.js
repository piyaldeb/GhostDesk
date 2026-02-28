/**
 * GhostPC WhatsApp Bridge
 * Runs as a local HTTP server that exposes WhatsApp Web via REST API.
 *
 * Setup:
 *   npm install whatsapp-web.js express qrcode-terminal
 *   node whatsapp_bridge.js
 *
 * Scan the QR code with WhatsApp → Done.
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const express = require('express');
const qrcode = require('qrcode-terminal');

const PORT = 3099;
const app = express();
app.use(express.json());

let client = null;
let clientReady = false;

// ── Initialize WhatsApp Client ───────────────────────────────────────────────

function initClient() {
    client = new Client({
        authStrategy: new LocalAuth({ dataPath: './.whatsapp_session' }),
        puppeteer: {
            headless: true,
            args: ['--no-sandbox', '--disable-setuid-sandbox'],
        }
    });

    client.on('qr', (qr) => {
        console.log('\n📱 Scan this QR code with WhatsApp:\n');
        qrcode.generate(qr, { small: true });
    });

    client.on('ready', () => {
        clientReady = true;
        console.log('✅ WhatsApp connected!');
    });

    client.on('auth_failure', (msg) => {
        console.error('❌ Auth failure:', msg);
        clientReady = false;
    });

    client.on('disconnected', (reason) => {
        console.log('WhatsApp disconnected:', reason);
        clientReady = false;
    });

    // ── Incoming message hook → POST to Python auto-responder ──────────────
    client.on('message', async (msg) => {
        if (msg.fromMe) return;  // ignore sent messages
        if (!clientReady) return;

        try {
            const notifyName = msg._data?.notifyName || '';
            const payload = {
                contact: msg.from,
                contact_name: notifyName,
                body: msg.body || '',
                timestamp: new Date(msg.timestamp * 1000).toISOString(),
                type: msg.type,
            };

            // Node 18+ has native fetch; older versions need node-fetch
            const fetchFn = typeof fetch !== 'undefined' ? fetch : require('node-fetch');
            await fetchFn('http://localhost:3100/incoming/whatsapp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        } catch (err) {
            // Python server may not be listening yet — silently ignore
            if (process.env.DEBUG) console.error('Webhook post failed:', err.message);
        }
    });

    client.initialize();
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function normalizeNumber(contact) {
    // If it's already a full chat ID, return as-is
    if (contact.includes('@c.us') || contact.includes('@g.us')) return contact;
    // Strip non-digits
    const digits = contact.replace(/\D/g, '');
    return `${digits}@c.us`;
}

// ── Routes ───────────────────────────────────────────────────────────────────

app.get('/status', (req, res) => {
    res.json({ ready: clientReady, status: clientReady ? 'connected' : 'disconnected' });
});

app.get('/messages', async (req, res) => {
    if (!clientReady) return res.json({ success: false, error: 'Not connected' });
    try {
        const { contact, limit = 20 } = req.query;
        const chatId = normalizeNumber(contact);
        const chat = await client.getChatById(chatId);
        const messages = await chat.fetchMessages({ limit: parseInt(limit) });

        res.json({
            success: true,
            messages: messages.map(m => ({
                id: m.id._serialized,
                body: m.body,
                fromMe: m.fromMe,
                timestamp: new Date(m.timestamp * 1000).toISOString(),
                type: m.type,
            }))
        });
    } catch (e) {
        res.json({ success: false, error: e.message });
    }
});

app.post('/send', async (req, res) => {
    if (!clientReady) return res.json({ success: false, error: 'Not connected' });
    try {
        const { contact, message } = req.body;
        const chatId = normalizeNumber(contact);
        await client.sendMessage(chatId, message);
        res.json({ success: true });
    } catch (e) {
        res.json({ success: false, error: e.message });
    }
});

app.get('/unread', async (req, res) => {
    if (!clientReady) return res.json({ success: false, error: 'Not connected' });
    try {
        const chats = await client.getChats();
        const unread = chats
            .filter(c => c.unreadCount > 0)
            .map(c => ({
                id: c.id._serialized,
                name: c.name,
                unread_count: c.unreadCount,
                last_message: c.lastMessage ? c.lastMessage.body : '',
            }));
        res.json({ success: true, chats: unread });
    } catch (e) {
        res.json({ success: false, error: e.message });
    }
});

app.get('/contacts', async (req, res) => {
    if (!clientReady) return res.json({ success: false, error: 'Not connected' });
    try {
        const contacts = await client.getContacts();
        res.json({
            success: true,
            contacts: contacts
                .filter(c => c.isMyContact)
                .map(c => ({
                    name: c.pushname || c.name || 'Unknown',
                    number: c.number,
                    id: c.id._serialized,
                }))
        });
    } catch (e) {
        res.json({ success: false, error: e.message });
    }
});

app.post('/send-file', async (req, res) => {
    if (!clientReady) return res.json({ success: false, error: 'Not connected' });
    try {
        const { contact, file_path, caption = '' } = req.body;
        const { MessageMedia } = require('whatsapp-web.js');
        const chatId = normalizeNumber(contact);
        const media = MessageMedia.fromFilePath(file_path);
        await client.sendMessage(chatId, media, { caption });
        res.json({ success: true });
    } catch (e) {
        res.json({ success: false, error: e.message });
    }
});

// ── Start ─────────────────────────────────────────────────────────────────────

app.listen(PORT, () => {
    console.log(`👻 GhostPC WhatsApp Bridge listening on port ${PORT}`);
    initClient();
});
