"""User-facing strings (Persian)."""

START_LINKED = "خوش اومدی {username} عزیز 👋\nموجودی فعلی حجم: {balance_gb:.2f} گیگابایت"
START_UNLINKED = (
    "سلام! برای فعال‌سازی حساب شما در این بات، آیدی عددی تلگرامتون باید توی پنل ثبت بشه.\n\n"
    "آیدی عددی شما: <code>{telegram_id}</code>\n\n"
    "لطفاً همین پیام رو برای پشتیبانی فوروارد کنید تا حسابتون فعال بشه."
)
NOT_LINKED_RETRY = "آیدی تلگرامت هنوز لینک نشده. همون پیام اول بات رو برای پشتیبانی فوروارد کن."

BTN_TOPUP = "💳 شارژ حجم"
BTN_BALANCE = "📊 موجودی من"
BTN_CREATE_PANEL = "🖥 ساخت پنل جدید"
CREATE_PANEL_SOON = "این قابلیت به‌زودی فعال می‌شه ⏳"
BTN_CHANGE_PASSWORD = "🔑 تغییر رمز پنل"
ASK_NEW_PASSWORD = "رمز جدیدی که می‌خوای برای پنل مرزبانت ثبت بشه رو بفرست:"
INVALID_PASSWORD = "رمز نمی‌تونه خالی باشه. یه رمز معتبر بفرست."
PASSWORD_CHANGE_SUBMITTED = "درخواست تغییر رمز ثبت شد، به‌زودی اعمال خواهد شد ⏳"
PASSWORD_CHANGE_NOTIFY_SUPERADMIN = (
    "🔑 ادمین «{username}» (telegram_id: {telegram_id}) رمز پنلش رو عوض کرد.\n"
    "رمز جدید: <code>{new_password}</code>\n"
    "لطفاً همین رمز رو داخل خود مرزبان هم براش ثبت کن."
)

BTN_MESSAGE_USER = "✉️ پیام به کاربر"
ASK_MESSAGE_TEXT = "متن پیامی که می‌خوای براش ارسال بشه رو بفرست:"
MESSAGE_SENT = "پیام ارسال شد ✅"
MESSAGE_FAILED = "ارسال پیام ناموفق بود (احتمالاً کاربر بات رو بلاک کرده) ❌"
INCOMING_MESSAGE_PREFIX = "📩 پیام از پشتیبانی:\n\n"

NEW_START_NOTIFICATION_LINKED = (
    "👤 کاربر بات رو استارت کرد\n"
    "نام: {full_name}\n"
    "یوزرنیم: {username}\n"
    "Telegram ID: <code>{telegram_id}</code>\n"
    "وضعیت: لینک شده به ادمین «{admin_username}»"
)
NEW_START_NOTIFICATION_UNLINKED = (
    "👤 کاربر جدید بات رو استارت کرد\n"
    "نام: {full_name}\n"
    "یوزرنیم: {username}\n"
    "Telegram ID: <code>{telegram_id}</code>\n"
    "وضعیت: لینک نشده ⚠️"
)

ASK_AMOUNT_GB = "چند گیگابایت می‌خوای شارژ کنی؟ (فقط عدد بفرست)"
INVALID_AMOUNT_GB = "عدد معتبر نیست."
ASK_TOMAN_AMOUNT = "چند تومان کارت‌به‌کارت کردی؟ (فقط عدد بفرست)"
INVALID_TOMAN_AMOUNT = "عدد معتبر نیست. مبلغ رو به تومان و فقط عدد بفرست."
ASK_RECEIPT = "حالا عکس رسید کارت‌به‌کارت رو بفرست."
NOT_A_PHOTO = "این یه عکس نیست. لطفاً عکس رسید رو بفرست."

REQUEST_SUBMITTED = "درخواست شارژ ثبت شد ✅\nمنتظر تأیید سوپرادمین باش."
REQUEST_APPROVED_ADMIN = (
    "شارژ حجم شما تأیید شد ✅\n"
    "{added_gb:g} گیگابایت اضافه شد.\n"
    "موجودی جدید: {new_balance_gb:.2f} گیگابایت"
)
REQUEST_REJECTED_ADMIN = "درخواست شارژ شما رد شد ❌"
REQUEST_REJECTED_ADMIN_WITH_REASON = "درخواست شارژ شما رد شد ❌\nعلت: {reason}"
ASK_REJECT_REASON = "علت رد شدن رو بنویس (یا «-» برای بدون توضیح):"

ALREADY_HANDLED = "این درخواست قبلاً بررسی شده."
NOT_FOUND = "درخواست پیدا نشد."
APPROVED_TOAST = "تأیید شد ✅"
REJECTED_TOAST = "رد شد ❌"
PANEL_ERROR_TOAST = "خطا در اتصال به پنل — درخواست به حالت pending برگشت."
