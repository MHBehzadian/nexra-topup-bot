"""User-facing strings (formal Persian)."""

START_LINKED = (
    "با سلام {name} عزیز 👋\n"
    "به ربات مدیریت پنل خوش آمدید.\n\n"
    "برای مشاهده‌ی پنل‌ها و موجودی هرکدام، «🖥 پنل‌های من» را انتخاب نمایید."
)
BALANCE_TEXT = "📊 موجودی حجم شما: {remaining_gb:.2f} / {initial_gb:.2f} گیگابایت (باقی‌مانده / کل اعتبار)"
START_UNLINKED = (
    "با سلام. برای فعال‌سازی حساب شما در این ربات، لازم است آیدی عددی تلگرام شما در پنل ثبت شود.\n\n"
    "آیدی عددی شما: <code>{telegram_id}</code>\n\n"
    "لطفاً همین پیام را برای پشتیبانی فوروارد نمایید تا حساب شما فعال شود."
)
NOT_LINKED_RETRY = "⚠️ آیدی تلگرام شما هنوز در پنل ثبت نشده است. لطفاً همان پیام ابتدایی ربات را برای پشتیبانی فوروارد نمایید."
PANEL_UNREACHABLE = "⚠️ در حال حاضر ارتباط با پنل برقرار نشد. لطفاً چند دقیقه دیگر تلاش نمایید."

BTN_CANCEL = "❌ انصراف"
CANCELLED = "🚫 عملیات لغو شد."

BTN_TOPUP = "💳 شارژ حجم"
BTN_BALANCE = "📊 موجودی من"
BTN_CREATE_PANEL = "🖥 ساخت پنل جدید"
CREATE_PANEL_SOON = "⏳ این امکان به‌زودی فعال خواهد شد."
BTN_CHANGE_PASSWORD = "🔑 تغییر رمز پنل"
ASK_CURRENT_PASSWORD = "🔒 برای تغییر رمز، ابتدا رمز عبور فعلی پنل خود را وارد نمایید:"
ASK_NEW_PASSWORD = "🔑 اکنون رمز عبور جدید را وارد نمایید:"
INVALID_PASSWORD = "⚠️ رمز عبور نمی‌تواند خالی باشد. لطفاً یک رمز عبور معتبر ارسال نمایید."
CURRENT_PASSWORD_WRONG = "⛔ رمز عبور فعلی نادرست است. عملیات لغو شد."
PASSWORD_CHANGE_FAILED = "⚠️ تغییر رمز ناموفق بود: {error}"
PASSWORD_APPLIED_ADMIN = "✅ رمز عبور پنل «{username}» با موفقیت تغییر کرد."
PASSWORD_CHANGE_NOTIFY_SUPERADMIN = (
    "🔑 ادمین «{username}» (آیدی عددی: {telegram_id}) رمز عبور پنل خود را تغییر داد.\n"
    "رمز جدید: <code>{new_password}</code>"
)

BTN_MESSAGE_USER = "✉️ پیام به کاربر"
ASK_MESSAGE_TEXT = "✉️ لطفاً متن پیامی که مایل به ارسال آن هستید را بنویسید:"
MESSAGE_SENT = "✅ پیام با موفقیت ارسال شد."
MESSAGE_FAILED = "⚠️ ارسال پیام ناموفق بود. احتمالاً کاربر ربات را مسدود کرده است."
INCOMING_MESSAGE_PREFIX = "📩 پیام از پشتیبانی:\n\n"

NEW_START_NOTIFICATION_LINKED = (
    "👤 کاربری ربات را استارت کرد\n"
    "نام: {full_name}\n"
    "یوزرنیم: {username}\n"
    "آیدی عددی: <code>{telegram_id}</code>\n"
    "وضعیت: متصل به ادمین «{admin_username}» ✅"
)
NEW_START_NOTIFICATION_UNLINKED = (
    "👤 کاربر جدیدی ربات را استارت کرد\n"
    "نام: {full_name}\n"
    "یوزرنیم: {username}\n"
    "آیدی عددی: <code>{telegram_id}</code>\n"
    "وضعیت: متصل نشده ⚠️"
)

SUPERADMIN_WELCOME = (
    "با سلام سوپرادمین محترم 👋\n"
    "با استارت هر کاربر جدید، یا ثبت درخواست شارژ/تغییر رمز، پیامی برای شما ارسال خواهد شد "
    "و می‌توانید مستقیماً از همان پیام نسبت به تأیید، رد یا ارسال پیام اقدام نمایید.\n\n"
    "درخواست‌های شارژ در انتظار بررسی و تنظیمات ربات نیز از دکمه‌های زیر در دسترس است."
)
BTN_PENDING_REQUESTS = "📋 درخواست‌های در انتظار"
NO_PENDING_REQUESTS = "ℹ️ در حال حاضر درخواست شارژ در انتظاری وجود ندارد."

FORCE_JOIN_TEXT = "📢 برای استفاده از ربات، ابتدا در کانال زیر عضو شوید و سپس «✅ عضو شدم» را بزنید."
FORCE_JOIN_CONFIRMED = "✅ عضویت شما تأیید شد. برای ادامه، دستور /start را ارسال نمایید."
BTN_TOGGLE_FORCE_JOIN = "🔛 روشن/خاموش‌کردن جوین اجباری"
BTN_SET_FORCE_JOIN_CHANNEL = "📢 تنظیم کانال جوین اجباری"
ASK_FORCE_JOIN_CHANNEL = "📢 لطفاً آیدی کانال را وارد نمایید (مثال: @channelusername):"
INVALID_CHANNEL = "⚠️ آیدی کانال معتبر نیست؛ باید با @ شروع شود."
FORCE_JOIN_CHANNEL_SET = "✅ کانال جوین اجباری با موفقیت روی {channel} تنظیم شد."
FORCE_JOIN_NO_CHANNEL_YET = "⚠️ ابتدا باید یک کانال برای جوین اجباری تنظیم نمایید."
FORCE_JOIN_ENABLED_ON = "جوین اجباری فعال شد ✅"
FORCE_JOIN_ENABLED_OFF = "جوین اجباری غیرفعال شد ⛔"

BTN_SET_PRICE = "💰 تنظیم قیمت هر گیگابایت"
ASK_PRICE_PER_GB = "💰 لطفاً قیمت هر گیگابایت را به تومان وارد نمایید:"
INVALID_PRICE = "⚠️ عدد وارد شده معتبر نیست."
PRICE_SET_CONFIRM = "✅ قیمت هر گیگابایت با موفقیت روی {price:,} تومان تنظیم شد."

BTN_SET_CARD = "💳 تنظیم شماره کارت"
ASK_CARD_NUMBER = "💳 لطفاً شماره کارت جدید را وارد نمایید:"
INVALID_CARD_NUMBER = "⚠️ شماره کارت نمی‌تواند خالی باشد."
CARD_SET_CONFIRM = "✅ شماره کارت با موفقیت به‌روزرسانی شد."

BTN_SYNC_TELEGRAM_IDS = "🔄 همگام‌سازی آیدی از مرزبان"
SYNC_RUNNING = "⏳ در حال دریافت اطلاعات از مرزبان..."
SYNC_RESULT_NONE = "ℹ️ هیچ ادمین جدیدی برای همگام‌سازی پیدا نشد (یا آیدی‌ها از قبل ثبت شده، یا تو مرزبان هم خالی‌اند)."
SYNC_RESULT_HEADER = "✅ {count} ادمین به‌روزرسانی شد:\n\n"
SYNC_RESULT_LINE = "• {username} ← <code>{telegram_id}</code>\n"
SYNC_FAILED = "⚠️ همگام‌سازی با خطا مواجه شد: {error}"

BTN_SET_BULK_PIN = "🔐 تنظیم پین امنیتی"
ASK_BULK_PIN_SET = "🔐 لطفاً یک پین امنیتی برای دریافت رمز ادمین‌ها تعیین نمایید:"
INVALID_BULK_PIN = "⚠️ پین نمی‌تواند خالی باشد."
BULK_PIN_SET_CONFIRM = "✅ پین امنیتی با موفقیت تنظیم شد."
BTN_EXPORT_ALL_PASSWORDS = "🔑 دریافت رمز همه ادمین‌ها"
ASK_BULK_PIN_ENTER = "🔐 برای دریافت رمزها، پین امنیتی را وارد نمایید:"
BULK_PIN_NOT_SET = "⚠️ ابتدا باید یک پین امنیتی تنظیم نمایید."
BULK_PIN_WRONG = "⛔ پین وارد شده نادرست است."
NO_CREDENTIALS = "ℹ️ هیچ ادمینی با رمز ثبت‌شده یافت نشد."
CREDENTIALS_LIST_HEADER = "🔑 رمز عبور ادمین‌ها:\n\n"
CREDENTIALS_LINE = "• {username} (آیدی: {telegram_id}): <code>{password}</code>\n"

ASK_AMOUNT_GB = "📶 لطفاً میزان حجم موردنیاز خود را به گیگابایت وارد نمایید:"
INVALID_AMOUNT_GB = "⚠️ عدد وارد شده معتبر نیست."
PRICE_NOT_SET = "⚠️ قیمت‌گذاری هنوز توسط پشتیبانی تنظیم نشده است. لطفاً بعداً تلاش نمایید یا با پشتیبانی تماس بگیرید."

INVOICE_TEXT = (
    "🧾 فاکتور شارژ حجم:\n\n"
    "مقدار: {gb:g} گیگابایت\n"
    "مبلغ قابل پرداخت: {price:,} تومان\n\n"
    "برای ادامه، پرداخت را انتخاب نمایید."
)
BTN_PAY = "💳 پرداخت"
PAYMENT_METHODS_TEXT = "💳 لطفاً روش پرداخت را انتخاب نمایید:"
BTN_PAY_CARD = "💳 کارت به کارت"
CARD_NOT_CONFIGURED = "⚠️ شماره کارت هنوز توسط پشتیبانی تنظیم نشده است. لطفاً با پشتیبانی تماس بگیرید."
CARD_PAYMENT_INSTRUCTIONS = (
    "💳 لطفاً مبلغ {price:,} تومان را به شماره کارت زیر واریز نمایید:\n\n"
    "<code>{card_number}</code>\n\n"
    "پس از واریز، تصویر رسید را ارسال نمایید."
)

BTN_PAY_WEEKLY = "🗓 پرداخت سر هفته"
WEEKLY_NOT_ENABLED = "⛔ این امکان برای شما فعال نیست!"
WEEKLY_TOPUP_SUCCESS = (
    "✅ {added_gb:g} گیگابایت به پنل «{username}» اضافه شد.\n"
    "📊 موجودی جدید: {new_gb:.2f} گیگابایت\n\n"
    "🗓 مبلغ {price:,} تومان به حساب این هفته‌ی شما اضافه شد.\n"
    "💳 بدهی فعلی: {debt:,} تومان"
)
WEEKLY_TOPUP_FAILED = "⚠️ ثبت شارژ ناموفق بود: {error}"
WEEKLY_REMINDER = (
    "🗓 یادآوری تسویه‌ی هفتگی\n\n"
    "🖥 پنل: {username}\n"
    "💰 مبلغ قابل پرداخت: {amount:,} تومان\n\n"
    "لطفاً تا پایان هفته نسبت به تسویه اقدام نمایید."
)
BTN_PAY_DEBT = "💳 پرداخت"
DEBT_PAYMENT_INSTRUCTIONS = (
    "💳 لطفاً مبلغ {amount:,} تومان را به شماره کارت زیر واریز نمایید:\n\n"
    "<code>{card_number}</code>\n\n"
    "پس از واریز، تصویر رسید را ارسال نمایید."
)
NO_DEBT = "✅ در حال حاضر بدهی‌ای ثبت نشده است."
SETTLEMENT_SUBMITTED = "⏳ رسید تسویه ثبت شد. پس از بررسی، بدهی شما تسویه خواهد شد."
SETTLEMENT_APPROVED_ADMIN = "✅ تسویه‌ی شما تأیید شد. بدهی پنل «{username}» صفر شد."

BTN_TOGGLE_WEEKLY = "🗓 فعال/غیرفعال‌کردن پرداخت هفتگی"
ASK_WEEKLY_USERNAME = "🗓 نام کاربری پنلی که می‌خواهید وضعیت پرداخت هفتگی‌اش تغییر کند را وارد نمایید:"
WEEKLY_ENABLED_ON = "✅ پرداخت هفتگی برای پنل «{username}» فعال شد."
WEEKLY_ENABLED_OFF = "⛔ پرداخت هفتگی برای پنل «{username}» غیرفعال شد."
WEEKLY_USED_NOTIFY_SUPERADMIN = (
    "🗓 خرید اعتباری (پرداخت سر هفته)\n\n"
    "🖥 پنل: {username}\n"
    "👤 آیدی عددی: {telegram_id}\n"
    "📶 حجم: {added_gb:g} گیگابایت\n"
    "💰 مبلغ: {price:,} تومان\n"
    "💳 مجموع بدهی: {debt:,} تومان"
)
WEEKLY_SETTLEMENT_LIST_HEADER = "🗓 تسویه‌ی هفتگی — وضعیت بدهی‌ها:\n\n"
WEEKLY_SETTLEMENT_LINE = "▫️ <b>{username}</b> — {amount:,} تومان{note}\n"
WEEKLY_SETTLEMENT_PAID_NOTE = " (از کیف پول تسویه شد ✅)"
WEEKLY_SETTLEMENT_NONE = "🗓 تسویه‌ی هفتگی: هیچ بدهی‌ای برای این هفته ثبت نشده است."
WEEKLY_WALLET_SETTLED = (
    "✅ بدهی هفتگی پنل «{username}» به مبلغ {paid:,} تومان از کیف پول شما تسویه شد.\n"
    "👛 موجودی کیف پول: {balance:,} تومان"
)
WEEKLY_WALLET_PARTIAL = (
    "🗓 زمان تسویه‌ی هفتگی رسید.\n\n"
    "🖥 پنل: {username}\n"
    "👛 از کیف پول کسر شد: {paid:,} تومان\n"
    "💰 باقی‌مانده جهت پرداخت: {remaining:,} تومان"
)

BTN_WALLET = "👛 کیف پول"
BTN_PAY_WALLET = "👛 پرداخت از کیف پول"
WALLET_BALANCE = "👛 موجودی کیف پول شما: {balance:,} تومان"
BTN_CHARGE_WALLET = "➕ شارژ کیف پول"
ASK_WALLET_AMOUNT = "➕ چه مبلغی (تومان) می‌خواهید به کیف پول اضافه کنید؟"
INVALID_WALLET_AMOUNT = "⚠️ مبلغ وارد شده معتبر نیست."
WALLET_CHARGE_INSTRUCTIONS = (
    "💳 لطفاً مبلغ {amount:,} تومان را به شماره کارت زیر واریز نمایید:\n\n"
    "<code>{card_number}</code>\n\n"
    "پس از واریز، تصویر رسید را ارسال نمایید."
)
WALLET_CHARGE_SUBMITTED = "⏳ رسید شارژ کیف پول ثبت شد و پس از بررسی اعمال خواهد شد."
WALLET_CHARGED_ADMIN = (
    "✅ کیف پول شما {amount:,} تومان شارژ شد.\n👛 موجودی جدید: {balance:,} تومان"
)
WALLET_INSUFFICIENT = (
    "⚠️ موجودی کیف پول کافی نیست.\n"
    "💰 مبلغ فاکتور: {price:,} تومان\n"
    "👛 موجودی شما: {balance:,} تومان"
)
WALLET_PAID_SUCCESS = (
    "✅ {added_gb:g} گیگابایت به پنل «{username}» اضافه شد.\n"
    "📊 موجودی جدید پنل: {new_gb:.2f} گیگابایت\n"
    "👛 موجودی کیف پول: {balance:,} تومان"
)
BTN_GRANT_WALLET = "👛 شارژ کیف پول کاربر"
ASK_GRANT_WALLET_ID = "👛 آیدی عددی کاربری که می‌خواهید کیف پولش شارژ شود را وارد نمایید:"
ASK_GRANT_WALLET_AMOUNT = "👛 چه مبلغی (تومان) به کیف پول این کاربر اضافه شود؟"
GRANT_WALLET_SUCCESS = "✅ کیف پول کاربر {telegram_id} شارژ شد.\n👛 موجودی جدید: {balance:,} تومان"

BTN_DEBTS = "💰 بدهی‌ها"
DEBTS_HEADER = "💰 بدهی‌های تسویه‌نشده:\n\n"
DEBT_LINE = "▫️ <b>{username}</b> — {amount:,} تومان\n"
NO_DEBTS_AT_ALL = "✅ هیچ بدهی تسویه‌نشده‌ای وجود ندارد."

ASK_RECEIPT = "🧾 لطفاً تصویر رسید واریز را ارسال نمایید."
NOT_A_PHOTO = "⚠️ فایل ارسالی تصویر نیست. لطفاً تصویر رسید را ارسال نمایید."

REQUEST_SUBMITTED = "⏳ درخواست شارژ شما ثبت شد. به‌زودی رسید شما بررسی خواهد شد."
REQUEST_APPROVED_ADMIN = (
    "✅ درخواست شارژ حجم شما تأیید شد.\n"
    "{added_gb:g} گیگابایت به حساب شما اضافه شد.\n"
    "موجودی جدید: {new_balance_gb:.2f} گیگابایت"
)
REQUEST_REJECTED_ADMIN = "❌ درخواست شارژ حجم شما رد شد."
REQUEST_REJECTED_ADMIN_WITH_REASON = "❌ درخواست شارژ حجم شما رد شد.\nعلت: {reason}"
ASK_REJECT_REASON = "📝 لطفاً علت رد درخواست را بنویسید (یا «-» در صورت عدم نیاز به توضیح):"

ALREADY_HANDLED = "ℹ️ این درخواست قبلاً بررسی شده است."
NOT_FOUND = "⚠️ درخواست یافت نشد."
APPROVED_TOAST = "تأیید شد ✅"
REJECTED_TOAST = "رد شد ❌"
PANEL_ERROR_TOAST = "⚠️ خطا در اتصال به پنل. درخواست به حالت در انتظار بازگشت."

BTN_MY_PANELS = "🖥 پنل‌های من"
NO_PANELS = "ℹ️ هیچ پنلی به حساب شما متصل نیست."
PANELS_LIST_HEADER = "🖥 پنل‌های شما:\n\n"
PANEL_LINE = (
    "▫️ <b>{username}</b>\n"
    "   📊 موجودی: {remaining_gb:.2f} / {initial_gb:.2f} گیگابایت\n"
    "   {expiry_line}\n"
)
PANEL_EXPIRY_LINE = "📅 انقضا: {expiry}"
PANEL_NO_EXPIRY = "📅 بدون تاریخ انقضا"
CHOOSE_PANEL = "🖥 لطفاً پنل موردنظر را انتخاب نمایید:"

WARN_100 = (
    "⚠️ حجم پنل «{username}» رو به اتمام است.\n"
    "📊 باقی‌مانده: {remaining_gb:.2f} گیگابایت\n\n"
    "برای جلوگیری از قطعی، پنل خود را شارژ نمایید."
)
WARN_50 = (
    "🔔 حجم پنل «{username}» کمتر از ۵۰ گیگابایت است.\n"
    "📊 باقی‌مانده: {remaining_gb:.2f} گیگابایت\n\n"
    "لطفاً نسبت به شارژ پنل اقدام نمایید."
)
WARN_10 = (
    "🚨 حجم پنل «{username}» کمتر از ۱۰ گیگابایت است!\n"
    "📊 باقی‌مانده: {remaining_gb:.2f} گیگابایت\n\n"
    "در صورت عدم شارژ، به‌زودی امکان ساخت کاربر جدید را نخواهید داشت."
)
WARN_EMPTY = (
    "⛔ حجم پنل «{username}» به پایان رسید.\n\n"
    "برای ادامه‌ی سرویس‌دهی، لطفاً پنل خود را شارژ نمایید."
)
BTN_TOPUP_THIS_PANEL = "💳 شارژ پنل"

BTN_ALL_PANELS = "🗂 همه پنل‌ها"
ALL_PANELS_HEADER = "🗂 لیست کامل پنل‌ها ({count} مورد):\n\n"
ADMIN_PANEL_LINE = (
    "▫️ <b>{username}</b>{status}\n"
    "   📊 {remaining_gb:.2f} / {initial_gb:.2f} گیگابایت\n"
    "   👤 آیدی: {telegram_id}\n"
)
PANEL_INACTIVE_MARK = " (غیرفعال ⛔)"
BTN_GRANT_TRAFFIC = "➕ افزودن حجم"
ASK_GRANT_USERNAME = "➕ نام کاربری پنلی که می‌خواهید شارژ شود را وارد نمایید:"
ASK_GRANT_AMOUNT = "➕ چند گیگابایت به پنل «{username}» اضافه شود؟"
GRANT_SUCCESS = (
    "✅ {added_gb:g} گیگابایت به پنل «{username}» اضافه شد.\n"
    "📊 موجودی جدید: {new_gb:.2f} گیگابایت"
)
GRANT_FAILED = "⚠️ افزودن حجم ناموفق بود: {error}"
GRANT_NOTIFY_ADMIN = (
    "🎁 حجم پنل «{username}» توسط پشتیبانی افزایش یافت.\n"
    "➕ {added_gb:g} گیگابایت اضافه شد.\n"
    "📊 موجودی جدید: {new_gb:.2f} گیگابایت"
)

BTN_BROADCAST = "📣 پیام همگانی"
ASK_BROADCAST_TEXT = "📣 متن پیامی که برای همه‌ی کاربران ارسال شود را بنویسید:"
BROADCAST_RESULT = "📣 پیام همگانی ارسال شد.\n✅ موفق: {sent}\n❌ ناموفق: {failed}"
BROADCAST_PREFIX = "📣 اطلاعیه:\n\n"

BTN_TUTORIALS = "📚 آموزش‌ها"
NO_TUTORIALS = "ℹ️ هنوز آموزشی ثبت نشده است."
TUTORIALS_LIST_TEXT = "📚 لطفاً آموزش موردنظر را انتخاب نمایید:"
BTN_ADD_TUTORIAL = "➕ افزودن آموزش"
ASK_TUTORIAL_TITLE = "📚 لطفاً عنوان آموزش را وارد نمایید:"
ASK_TUTORIAL_CONTENT = (
    "📎 لطفاً محتوای آموزش را ارسال نمایید. می‌تواند متن، عکس، ویدیو یا فایل باشد "
    "(برای عکس/ویدیو/فایل می‌توانید توضیح هم اضافه نمایید)."
)
INVALID_TUTORIAL_CONTENT = "⚠️ نوع محتوای ارسالی پشتیبانی نمی‌شود. لطفاً متن، عکس، ویدیو یا فایل ارسال نمایید."
TUTORIAL_ADDED_CONFIRM = "✅ آموزش «{title}» با موفقیت اضافه شد."
