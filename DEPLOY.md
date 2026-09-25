# رحمة — نشر البوت وربطه بلوحة مستقلة

يشغل هذا المشروع **بوت رحمة فقط**. شغّله دائماً على هوست Discord bot مستقل عن هوست لوحة التحكم، مع إبقاء الاتصال الصوتي وFFmpeg وDiscord bot token على هوست البوت. إعداد لوحة الويب وOAuth موجود في المشروع المنفصل `rahma-dashboard/README.md`.

## 1. إنشاء التطبيق ودعوة البوت

1. أنشئ Discord application في [Discord Developer Portal](https://discord.com/developers/applications)، وأنشئ البوت وخزّن التوكن في مدير أسرار هوست البوت فقط.
2. فعّل `bot` و`applications.commands` للتثبيت على السيرفر. احتياجات الأذونات: View Channel، Send Messages، Embed Links، Attach Files، Connect، Speak، وUse Voice Activity (إذا احتاجها مشغل الصوت). لا يحتاج البوت إلى Message Content Intent.
3. لا تشارك bot token مع لوحة التحكم أو صاحبها؛ إعدادات لوحة الويب تستخدم OAuth منفصلاً لا يطلب صلاحية إرسال رسائل باسم المشرف.

## 2. استضافة البوت

على Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y git ffmpeg python3 python3-venv fonts-noto-core
sudo mkdir -p /opt/rahma-discord-bot
sudo chown "$USER":"$USER" /opt/rahma-discord-bot
git clone YOUR_REPOSITORY_URL /opt/rahma-discord-bot
cd /opt/rahma-discord-bot
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

أنشئ `.env` داخل الهوست، واحتفظ به بصلاحيات مقيدة `chmod 600 .env`. عيّن على الأقل:

```dotenv
DISCORD_TOKEN=<bot-token محفوظ في مدير الأسرار>
DATABASE_PATH=data/rahma.sqlite3
COMMAND_SYNC_GUILD_ID=<اختياري للتجربة السريعة>
```

يفضل تشغيل bot worker وخدمة API المضمنة تحت systemd أو container supervisor. ملف `systemd/rahma-discord-bot.service` يشغل العملية على طول ويعيد تشغيلها عند الخروج. تأكد أن مجلد `data/` قابل للكتابة، وأن `ffmpeg -version` و`.venv/bin/python -c ...` يعملان على هوستك؛ نحتاج FFmpeg والاعتماديات الصوتية لاختبار بث الصوت الفعلي.

## 3. تجهيز API الخاص باللوحة

لا تُفعّل API قبل أن يوجد هوست لوحة ثابت ونطاقه معروف. من secret manager في **هوست البوت** أضف:

```dotenv
DASHBOARD_SHARED_SECRET=<قيمة عشوائية سرية لا تقل عن 32 بايت؛ تطابق BOT_API_SHARED_SECRET في اللوحة>
DASHBOARD_API_HOST=127.0.0.1
DASHBOARD_API_PORT=8787
```

أنشئ سر HMAC عشوائياً مثل `openssl rand -base64 48`، وضع النسخة نفسها في المتغيرين `DASHBOARD_SHARED_SECRET` في البوت و`BOT_API_SHARED_SECRET` في اللوحة. هذا المفتاح **مختلف** عن `DASHBOARD_SESSION_SECRET` في مضيف لوحة الويب. لا تكتبه في Git أو Discord أو المحادثة، ولا تطبعه في سجلات الخدمة. يجب أن يكون ثابتاً للسيرفرين؛ تغييره يتطلب تحديث الجانبين وإعادة تشغيلهما.

الافتراضي `127.0.0.1` آمن إذا كان reverse proxy على مضيف البوت نفسه. لكن إذا اللوحة والبوت مستضافان في مضيفين مختلفين، لا يستطيع المضيف الآخر الوصول إلى loopback. أفضل خيار هو private VPN/wireguard/Tailscale؛ اربط الـAPI بعنوان VPN/واجهة خاصة وأضف firewall يسمح فقط بعنوان أو subnet لوحة التحكم. إذا لزم HTTPS عام، استخدم نطاقاً ثابتاً وشهادة TLS وreverse proxy، وقيد الجدار الناري للوصول من عنوان هوست اللوحة، واستخدم HMAC كما هو. **لا تفتح `8787` للعالم.** خادم اللوحة يرفض روابط HTTP العامة، ولا ترسل سر HMAC إلى المتصفح.

بعد التهيئة، إذا تعذّر الوصول تعرض اللوحة حالة الاتصال وتفاصيل الخطأ؛ تحقّق من الربط عبر VPN، TLS، DNS، المنفذ وتزامن الوقت. استجابة API محمية بتوقيع HMAC-SHA256 زمني، nonce للاستخدام مرة واحدة، hash لجسم الطلب والمسار والمشغّل. كل طلبات البوت تتطلب توقيعاً؛ الطلبات اليدوية غير الموقعة تُرفض. لا تحتاج لاتصال CORS من browser إلى bot.

## 4. أول إعداد Discord

1. شغّل البوت وسجّل دخوله. استخدم `/setup prayer` لاختيار الموقع والمنطقة الزمنية وطريقة الحساب والمذهب والقنوات. صورة التنبيه تصل عند كل صلاة؛ صورة الجدول اليومي تصل مرة واحدة فقط في `timetable_time` (الافتراضي `06:00` بالتوقيت المحلي).
2. استخدم `/setup reminders` للقناة ووقت الأذكار والدعاء اليومي وتذكير الجمعة. المحتوى والمصادر داخل الصور. البديل النصي لقارئ الشاشة اختياري.
3. افتح `/quran browse` واختر قارئاً وإصدار مصحف/رواية متاحاً. لا تخلط رقم القارئ بمعرّف الإصدار. المكتبة تُجلب مباشرة من المصدر، وتصل جميع الخيارات عبر التصفح المرقّم.
4. استخدم `/setup quran` لاختيار روم البث، القارئ والإصدار. شغّل التشغيل التلقائي فقط إذا تريد بثاً مستمراً بعد إعادة تشغيل البوت. للختمة، اختر إصداراً يعرض 114 سورة.
5. يظل التحكم من Discord متاحاً عبر `/quran controls`، ومن لوحة رحمة في هوست منفصل بعد تفعيل Discord OAuth وHMAC. لوحة الويب تسمح فقط لصاحب السيرفر أو مشرف يملك Manage Server/Administrator.

## 5. حساب وإدارة الخدمة

```bash
sudo cp systemd/rahma-discord-bot.service /etc/systemd/system/rahma-discord-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now rahma-discord-bot
sudo systemctl status rahma-discord-bot
journalctl -u rahma-discord-bot -f
```

راجع إعدادات التوقيت المحلي ومصدر الحساب مع مسؤول السيرفر قبل تفعيل تنبيهات الصلاة؛ المواقيت الحسابية قد تختلف عن إعلان المسجد المحلي. احفظ نسخاً منتظمة من `data/rahma.sqlite3`؛ قاعدة البيانات تحفظ إعدادات السيرفر ومفاتيح منع تكرار التنبيهات، ولا تخزن توكن البوت أو مفاتيح اللوحة.

## الاختبارات

```bash
.venv/bin/python -m compileall -q .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/smoke_extensions.py
.venv/bin/python tests/smoke_sources.py
```
