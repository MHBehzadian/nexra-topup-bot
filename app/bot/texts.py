"""User-facing strings (formal Persian)."""

START_LINKED = (
    "با سلام {username} عزیز 👋\n"
    "موجودی حجم شما: {remaining_gb:.2f} / {initial_gb:.2f} گیگابایت (باقی‌مانده / کل اعتبار)"
)
BALANCE_TEXT = "موجودی حجم شما: {remaining_gb:.2f} / {initial_gb:.2f} گیگابایت (باقی‌مانده / کل اعتبار)"
START_UNLINKED = (
    "با سلام. برای فعال‌سازی حساب شما در این ربات، لازم است آیدی عددی تلگرام شما در پنل ثبت شود.\n\n"
    "آیدی عددی شما: <code>{telegram_id}</code>\n\n"
    "لطفاً همین پیام را برای پشتیبانی فوروارد نمایید تا حساب شما فعال شود."
)
NOT_LINKED_RETRY = "آیدی تلگرام شما هنوز در پنل ثبت نشده است. لطفاً همان پیام ابتدایی ربات را برای پشتیبانی فوروارد نمایید."

BTN_TOPUP = "💳 شارژ حجم"
BTN_BALANCE = "📊 موجودی من"
BTN_CREATE_PANEL = "🖥 ساخت پنل جدید"
CREATE_PANEL_SOON = "این امکان به‌زودی فعال خواهد شد."
BTN_CHANGE_PASSWORD = "🔑 تغییر رمز پنل"
ASK_NEW_PASSWORD = "لطفاً رمز عبور جدیدی که مایل به ثبت آن برای پنل مرزبان خود هستید را ارسال نمایید:"
INVALID_PASSWORD = "رمز عبور نمی‌تواند خالی باشد. لطفاً یک رمز عبور معتبر ارسال نمایید."
PASSWORD_CHANGE_SUBMITTED = "درخواست تغییر رمز عبور ثبت شد و به‌زودی اعمال خواهد شد."
PASSWORD_CHANGE_NOTIFY_SUPERADMIN_AUTO = (
    "🔑 رمز عبور پنل ادمین «{username}» (آیدی عددی: {telegram_id}) به‌صورت خودکار "
    "در مرزبان و نکسرا پنل به‌روزرسانی شد.\n"
    "رمز جدید: <code>{new_password}</code>"
)
PASSWORD_CHANGE_AUTO_FAILED_SUPERADMIN = (
    "⚠️ اعمال خودکار تغییر رمز برای ادمین «{username}» (آیدی عددی: {telegram_id}) ناموفق بود.\n"
    "خطا: {error}\n\n"
    "رمز درخواستی: <code>{new_password}</code>\n\n"
    "لطفاً ابتدا همین رمز را در خود مرزبان برای ایشان ثبت نمایید، سپس دکمه‌ی زیر را بزنید "
    "تا در نکسرا پنل نیز اعمال شود."
)
BTN_PASSWORD_APPLIED = "✅ اعمال شد"
PASSWORD_APPLIED_TOAST = "اعمال شد"
PASSWORD_APPLIED_ADMIN = "رمز عبور جدید شما با موفقیت اعمال شد."
PASSWORD_ALREADY_APPLIED = "این درخواست قبلاً اعمال شده است."

BTN_MESSAGE_USER = "✉️ پیام به کاربر"
ASK_MESSAGE_TEXT = "لطفاً متن پیامی که مایل به ارسال آن هستید را بنویسید:"
MESSAGE_SENT = "پیام با موفقیت ارسال شد."
MESSAGE_FAILED = "ارسال پیام ناموفق بود. احتمالاً کاربر ربات را مسدود کرده است."
INCOMING_MESSAGE_PREFIX = "📩 پیام از پشتیبانی:\n\n"

NEW_START_NOTIFICATION_LINKED = (
    "👤 کاربری ربات را استارت کرد\n"
    "نام: {full_name}\n"
    "یوزرنیم: {username}\n"
    "آیدی عددی: <code>{telegram_id}</code>\n"
    "وضعیت: متصل به ادمین «{admin_username}»"
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
NO_PENDING_REQUESTS = "در حال حاضر درخواست شارژ در انتظاری وجود ندارد."

FORCE_JOIN_TEXT = "برای استفاده از ربات، ابتدا در کانال زیر عضو شوید و سپس «✅ عضو شدم» را بزنید."
FORCE_JOIN_CONFIRMED = "عضویت شما تأیید شد. برای ادامه، دستور /start را ارسال نمایید."
BTN_TOGGLE_FORCE_JOIN = "🔛 روشن/خاموش‌کردن جوین اجباری"
BTN_SET_FORCE_JOIN_CHANNEL = "📢 تنظیم کانال جوین اجباری"
ASK_FORCE_JOIN_CHANNEL = "لطفاً آیدی کانال را وارد نمایید (مثال: @channelusername):"
INVALID_CHANNEL = "آیدی کانال معتبر نیست؛ باید با @ شروع شود."
FORCE_JOIN_CHANNEL_SET = "کانال جوین اجباری با موفقیت روی {channel} تنظیم شد."
FORCE_JOIN_NO_CHANNEL_YET = "ابتدا باید یک کانال برای جوین اجباری تنظیم نمایید."
FORCE_JOIN_ENABLED_ON = "جوین اجباری فعال شد ✅"
FORCE_JOIN_ENABLED_OFF = "جوین اجباری غیرفعال شد ⛔"

BTN_SET_PRICE = "💰 تنظیم قیمت هر گیگابایت"
ASK_PRICE_PER_GB = "لطفاً قیمت هر گیگابایت را به تومان وارد نمایید:"
INVALID_PRICE = "عدد وارد شده معتبر نیست."
PRICE_SET_CONFIRM = "قیمت هر گیگابایت با موفقیت روی {price:,} تومان تنظیم شد."

BTN_SET_CARD = "💳 تنظیم شماره کارت"
ASK_CARD_NUMBER = "لطفاً شماره کارت جدید را وارد نمایید:"
INVALID_CARD_NUMBER = "شماره کارت نمی‌تواند خالی باشد."
CARD_SET_CONFIRM = "شماره کارت با موفقیت به‌روزرسانی شد."

ASK_AMOUNT_GB = "لطفاً میزان حجم موردنیاز خود را به گیگابایت وارد نمایید:"
INVALID_AMOUNT_GB = "عدد وارد شده معتبر نیست."
PRICE_NOT_SET = "قیمت‌گذاری هنوز توسط پشتیبانی تنظیم نشده است. لطفاً بعداً تلاش نمایید یا با پشتیبانی تماس بگیرید."

INVOICE_TEXT = (
    "فاکتور شارژ حجم:\n\n"
    "مقدار: {gb:g} گیگابایت\n"
    "مبلغ قابل پرداخت: {price:,} تومان\n\n"
    "برای ادامه، پرداخت را انتخاب نمایید."
)
BTN_PAY = "💳 پرداخت"
PAYMENT_METHODS_TEXT = "لطفاً روش پرداخت را انتخاب نمایید:"
BTN_PAY_CARD = "💳 کارت به کارت"
CARD_NOT_CONFIGURED = "شماره کارت هنوز توسط پشتیبانی تنظیم نشده است. لطفاً با پشتیبانی تماس بگیرید."
CARD_PAYMENT_INSTRUCTIONS = (
    "لطفاً مبلغ {price:,} تومان را به شماره کارت زیر واریز نمایید:\n\n"
    "<code>{card_number}</code>\n\n"
    "پس از واریز، تصویر رسید را ارسال نمایید."
)

ASK_RECEIPT = "لطفاً تصویر رسید واریز را ارسال نمایید."
NOT_A_PHOTO = "فایل ارسالی تصویر نیست. لطفاً تصویر رسید را ارسال نمایید."

REQUEST_SUBMITTED = "درخواست شارژ شما ثبت شد. به‌زودی رسید شما بررسی خواهد شد."
REQUEST_APPROVED_ADMIN = (
    "درخواست شارژ حجم شما تأیید شد.\n"
    "{added_gb:g} گیگابایت به حساب شما اضافه شد.\n"
    "موجودی جدید: {new_balance_gb:.2f} گیگابایت"
)
REQUEST_REJECTED_ADMIN = "درخواست شارژ حجم شما رد شد."
REQUEST_REJECTED_ADMIN_WITH_REASON = "درخواست شارژ حجم شما رد شد.\nعلت: {reason}"
ASK_REJECT_REASON = "لطفاً علت رد درخواست را بنویسید (یا «-» در صورت عدم نیاز به توضیح):"

ALREADY_HANDLED = "این درخواست قبلاً بررسی شده است."
NOT_FOUND = "درخواست یافت نشد."
APPROVED_TOAST = "تأیید شد"
REJECTED_TOAST = "رد شد"
PANEL_ERROR_TOAST = "خطا در اتصال به پنل. درخواست به حالت در انتظار بازگشت."

BTN_TUTORIALS = "📚 آموزش‌ها"
NO_TUTORIALS = "هنوز آموزشی ثبت نشده است."
TUTORIALS_LIST_TEXT = "لطفاً آموزش موردنظر را انتخاب نمایید:"
BTN_ADD_TUTORIAL = "➕ افزودن آموزش"
ASK_TUTORIAL_TITLE = "لطفاً عنوان آموزش را وارد نمایید:"
ASK_TUTORIAL_CONTENT = (
    "لطفاً محتوای آموزش را ارسال نمایید. می‌تواند متن، عکس، ویدیو یا فایل باشد "
    "(برای عکس/ویدیو/فایل می‌توانید توضیح هم اضافه نمایید)."
)
INVALID_TUTORIAL_CONTENT = "نوع محتوای ارسالی پشتیبانی نمی‌شود. لطفاً متن، عکس، ویدیو یا فایل ارسال نمایید."
TUTORIAL_ADDED_CONFIRM = "آموزش «{title}» با موفقیت اضافه شد."
