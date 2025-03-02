import sys
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    ContextTypes,
    ConversationHandler,
    filters
)
try:
    from config import BOT_TOKEN, SUPERVISOR_GROUP_ID, DUTY_OPS_GROUP_ID, SPREADSHEET_ID, CREDENTIALS_FILE
except ImportError:
    print("Error: Cannot find config.py")
    sys.exit(1)

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import json

# States for conversation
DATES = 0
HOURS = 1
REMARKS = 2

# Initialize Google Sheets API
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)

class LeaveRequest:
    def __init__(self, requester_id, requester_name, requester_handle, 
                 start_date, end_date, hours_per_day, remarks, request_id):
        self.requester_id = requester_id
        self.requester_name = requester_name
        self.requester_handle = requester_handle
        self.start_date = start_date
        self.end_date = end_date
        self.hours_per_day = hours_per_day
        self.remarks = remarks
        self.request_id = request_id
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.supervisor_approval = None
        self.supervisor_id = None

# function to check leave balance
async def check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check user's leave balance"""
    user = update.effective_user
    
    try:
        # Open the spreadsheet
        worksheet = client.open_by_key(SPREADSHEET_ID).sheet1
        
        # Find user's row by Telegram ID
        cell = worksheet.find(str(user.id))
        if cell:
            row = cell.row
            
            # Get user's leave balance
            balance = float(worksheet.cell(row, 4).value)
            
            # Get leave history for current month
            history_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Leave History")
            all_records = history_sheet.get_all_records()
            
            # Filter records for current user and current month
            current_month = datetime.now().strftime("%Y-%m")
            month_records = [
                record for record in all_records 
                if record.get('Telegram ID', '') == str(user.id) and 
                record.get('Timestamp', '').startswith(current_month)
            ]
            
            # Calculate total hours taken this month
            month_hours = sum(float(record.get('Total Hours', 0)) for record in month_records)
            
            # Prepare the response message
            message = (
                f"📊 Leave Balance Information\n\n"
                f"Current Balance: {balance:.1f} hours\n"
                f"Hours taken this month: {month_hours:.1f} hours\n\n"
            )
            
            # Add recent leave history if any
            if month_records:
                message += "Recent Leave History (This Month):\n"
                for record in month_records:
                    message += (
                        f"- {record.get('Start Date')} to {record.get('End Date')}: "
                        f"{record.get('Total Hours')} hours\n"
                        f"  Remarks: {record.get('Remarks')}\n"
                    )
            else:
                message += "No leave taken this month.\n"
            
            await update.message.reply_text(message)
            
        else:
            await update.message.reply_text(
                "❌ Error: Your Telegram ID is not found in the system.\n"
                "Please contact your administrator."
            )
            
    except Exception as e:
        print(f"Error checking balance: {e}")
        await update.message.reply_text(
            "❌ Error checking leave balance. Please try again later or contact administrator."
        )



def format_hours_display(leave_request):
    """Helper function to format hours display"""
    hours_display = []
    start_date = datetime.strptime(leave_request.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(leave_request.end_date, "%Y-%m-%d")
    
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        hours = leave_request.hours_per_day[date_str]
        date_display = current_date.strftime("%b %d")
        hours_display.append(f"- {date_display}: {hours} hours")
        current_date += timedelta(days=1)
    
    return hours_display

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    await update.message.reply_text(
        f"Welcome to the Leave Request Bot!\n\n"
        f"Your Telegram ID: {user.id}\n"
        f"Your Display Name: {user.full_name}\n"
        f"Your Username: @{user.username if user.username else 'not set'}\n\n"
        "Available commands:\n"
        "/request - Start a new leave request\n"
        "/balance - Check your leave balance\n"
        "/cancel - Cancel current leave request"
    )

async def request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the leave request process"""
    await update.message.reply_text(
        "Please enter the date(s) for your leave:\n"
        "Format: YYYY-MM-DD or YYYY-MM-DD to YYYY-MM-DD\n"
        "Example: 2025-02-15 or 2025-02-15 to 2025-02-17"
    )
    return DATES

async def handle_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle date input"""
    text = update.message.text
    try:
        if " to " in text:
            start_date_str, end_date_str = text.split(" to ")
            start_date = datetime.strptime(start_date_str.strip(), "%Y-%m-%d")
            end_date = datetime.strptime(end_date_str.strip(), "%Y-%m-%d")
        else:
            start_date = end_date = datetime.strptime(text.strip(), "%Y-%m-%d")
        
        if start_date > end_date:
            raise ValueError("Start date cannot be after end date")
            
        context.user_data['start_date'] = start_date.strftime("%Y-%m-%d")
        context.user_data['end_date'] = end_date.strftime("%Y-%m-%d")
        
        days = (end_date - start_date).days + 1
        
        if days == 1:
            await update.message.reply_text(
                "Please enter the hours for this day:\n"
                "Examples:\n"
                "- Full day: 8\n"
                "- Half day: 4"
            )
        else:
            await update.message.reply_text(
                f"Please enter the hours for each day ({days} days):\n"
                "Options:\n"
                f"1. Same hours each day: enter a single number (e.g., 8 for {days} full days)\n"
                f"2. Different hours: enter values separated by commas (e.g., 8,4 for full day then half day)\n\n"
                "Examples:\n"
                "- All full days: 8\n"
                "- Full then half: 8,4\n"
                "- Half then full: 4,8\n"
                "- Different hours each day: 8,4,8"
            )
        return HOURS
        
    except ValueError as e:
        await update.message.reply_text(
            "Invalid date format. Please use YYYY-MM-DD.\n"
            "Example: 2025-02-15 or 2025-02-15 to 2025-02-17"
        )
        return DATES

async def handle_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle hours input"""
    try:
        hours_input = update.message.text
        
        start_date = datetime.strptime(context.user_data['start_date'], "%Y-%m-%d")
        end_date = datetime.strptime(context.user_data['end_date'], "%Y-%m-%d")
        days = (end_date - start_date).days + 1
        
        hours_per_day = {}
        
        if ',' in hours_input:
            hours_list = hours_input.split(',')
            if len(hours_list) != days:
                await update.message.reply_text(
                    f"Please provide {days} values (one for each day), separated by commas.\n"
                    "Example: 8,4 for a full day followed by half day"
                )
                return HOURS
                
            for i, hours in enumerate(hours_list):
                current_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
                try:
                    hours_value = float(hours.strip())
                    if hours_value <= 0 or hours_value > 8:
                        raise ValueError
                    hours_per_day[current_date] = hours_value
                except ValueError:
                    await update.message.reply_text(
                        f"Invalid hours value: {hours}\n"
                        "Please enter numbers between 0 and 8"
                    )
                    return HOURS
        else:
            try:
                hours_value = float(hours_input)
                if hours_value <= 0 or hours_value > 8:
                    raise ValueError
                current_date = start_date
                while current_date <= end_date:
                    hours_per_day[current_date.strftime("%Y-%m-%d")] = hours_value
                    current_date += timedelta(days=1)
            except ValueError:
                await update.message.reply_text(
                    "Invalid hours. Please enter a number between 0 and 8.\n"
                    f"For different hours each day, use commas (e.g., 8,4 for {days} days)"
                )
                return HOURS
        
        context.user_data['hours_per_day'] = hours_per_day
        
        await update.message.reply_text(
            "Please enter any remarks:\n"
            "Purpose of leave, special instructions, etc.\n"
            "Or put NIL if no remarks."
        )
        return REMARKS
        
    except ValueError:
        await update.message.reply_text(
            "Invalid hours. Please enter a number between 0 and 8."
        )
        return HOURS
    
async def handle_remarks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle remarks and create leave request"""
    remarks = update.message.text
    user = update.effective_user
    request_id = f"REQ_{datetime.now().strftime('%Y%m%d%H%M%S')}_{user.id}"
    
    # Create leave request
    leave_request = LeaveRequest(
        user.id,
        user.full_name,
        user.username,
        context.user_data['start_date'],
        context.user_data['end_date'],
        context.user_data['hours_per_day'],
        remarks,
        request_id
    )
    
    # Store request
    if 'pending_requests' not in context.bot_data:
        context.bot_data['pending_requests'] = {}
    context.bot_data['pending_requests'][request_id] = leave_request
    
    # Notify supervisors
    await notify_supervisors(context, leave_request)
    
    # Format hours display for confirmation
    hours_display = format_hours_display(leave_request)
    total_hours = sum(leave_request.hours_per_day.values())
    
    # Confirm to user
    await update.message.reply_text(
        f"Your leave request has been submitted:\n"
        f"Dates: {context.user_data['start_date']} to {context.user_data['end_date']}\n"
        f"Hours:\n" + "\n".join(hours_display) + f"\n"
        f"Total Hours: {total_hours}\n"
        f"Remarks: {remarks}\n"
        f"Request ID: {request_id}\n\n"
        "Supervisors have been notified."
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the request process"""
    await update.message.reply_text("Leave request cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

async def notify_supervisors(context: ContextTypes.DEFAULT_TYPE, leave_request: LeaveRequest):
    """Send request to supervisor group"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"supervisor_approve_{leave_request.request_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"supervisor_reject_{leave_request.request_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    hours_display = format_hours_display(leave_request)
    total_hours = sum(leave_request.hours_per_day.values())
    
    message = (
        f"🔔 New Leave Request\n\n"
        f"From: {leave_request.requester_name} (@{leave_request.requester_handle})\n"
        f"Dates: {leave_request.start_date} to {leave_request.end_date}\n"
        f"Hours:\n" + "\n".join(hours_display) + f"\n"
        f"Total Hours: {total_hours}\n"
        f"Remarks: {leave_request.remarks}\n"
        f"Time: {leave_request.timestamp}"
    )
    
    try:
        await context.bot.send_message(
            chat_id=SUPERVISOR_GROUP_ID,
            text=message,
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Error notifying supervisors: {e}")

async def notify_duty_ops(context: ContextTypes.DEFAULT_TYPE, leave_request: LeaveRequest):
    """Send approved request to duty ops group"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"dutyops_approve_{leave_request.request_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"dutyops_reject_{leave_request.request_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    hours_display = format_hours_display(leave_request)
    total_hours = sum(leave_request.hours_per_day.values())
    
    message = (
        f"🔔 Leave Request for Final Approval\n\n"
        f"From: {leave_request.requester_name} (@{leave_request.requester_handle})\n"
        f"Dates: {leave_request.start_date} to {leave_request.end_date}\n"
        f"Hours:\n" + "\n".join(hours_display) + f"\n"
        f"Total Hours: {total_hours}\n"
        f"Remarks: {leave_request.remarks}\n"
        f"Approved by: {leave_request.supervisor_approval}\n"
        f"Time: {leave_request.timestamp}"
    )
    
    try:
        await context.bot.send_message(
            chat_id=DUTY_OPS_GROUP_ID,
            text=message,
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Error notifying duty ops: {e}")

async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle supervisor's and duty ops' responses"""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_', 2)
    if len(parts) != 3:
        await query.edit_message_text("Error: Invalid callback data format")
        return
    
    approver_type, action, request_id = parts
    request = context.bot_data['pending_requests'].get(request_id)
    
    if not request:
        await query.edit_message_text("Error: Request not found or already processed.")
        return
    
    # Handle supervisor approval
    if approver_type == "supervisor" and action == "approve":
        request.supervisor_approval = query.from_user.full_name
        request.supervisor_id = query.from_user.id
        
        # Notify Duty Ops
        await notify_duty_ops(context, request)
        
        await query.edit_message_text(
            f"✅ Leave request approved by supervisor.\n"
            f"Waiting for Duty Ops approval.\n"
            f"Request ID: {request_id}"
        )
        
    # Handle Duty Ops approval
    elif approver_type == "dutyops" and action == "approve":
        try:
            worksheet = client.open_by_key(SPREADSHEET_ID).sheet1
            
            cell = worksheet.find(str(request.requester_id))
            if cell:
                row = cell.row
                total_hours = sum(request.hours_per_day.values())
                
                # Update leave balance
                current_balance = float(worksheet.cell(row, 4).value)
                new_balance = current_balance - total_hours
                worksheet.update_cell(row, 4, new_balance)
                
                # Format hours for history
                hours_breakdown = ",".join(str(h) for h in request.hours_per_day.values())
                
                history_sheet = client.open_by_key(SPREADSHEET_ID).worksheet("Leave History")
                history_sheet.append_row([
                    request.timestamp,
                    request.requester_name,
                    request.requester_handle,
                    request.start_date,
                    request.end_date,
                    hours_breakdown,
                    total_hours,
                    request.remarks,
                    request_id,
                    request.supervisor_approval,
                    query.from_user.full_name
                ])
                
                # Notify user of approval
                hours_display = format_hours_display(request)
                await context.bot.send_message(
                    chat_id=request.requester_id,
                    text=f"✅ Your leave request has been fully approved!\n"
                          f"Dates: {request.start_date} to {request.end_date}\n"
                          f"Hours:\n" + "\n".join(hours_display) + f"\n"
                          f"Total hours: {total_hours}\n"
                          f"Approved by:\n"
                          f"Supervisor: {request.supervisor_approval}\n"
                          f"Duty Ops: {query.from_user.full_name}\n"
                          f"Updated leave balance: {new_balance} hours"
                )
                
                await query.edit_message_text(
                    f"✅ Leave request fully approved and processed.\n"
                    f"Request ID: {request_id}"
                )
                
                # Remove from pending requests
                del context.bot_data['pending_requests'][request_id]
                
            else:
                raise Exception("User not found in leave balance sheet")
                
        except Exception as e:
            print(f"Error processing approval: {e}")
            await query.edit_message_text(
                f"❌ Error processing approval: {str(e)}\n"
                f"Request ID: {request_id}"
            )
            
    # Handle rejections from either supervisor or duty ops
    elif action == "reject":
        rejected_by = "Supervisor" if approver_type == "supervisor" else "Duty Ops"
        await context.bot.send_message(
            chat_id=request.requester_id,
            text=f"❌ Your leave request has been rejected by {rejected_by}.\n"
                 f"Dates: {request.start_date} to {request.end_date}"
        )
        await query.edit_message_text(
            f"❌ Leave request rejected by {rejected_by}.\n"
            f"Request ID: {request_id}"
        )
        del context.bot_data['pending_requests'][request_id]

def main():
    """Run the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Create conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('request', request_command)],
        states={
            DATES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dates)],
            HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_hours)],
            REMARKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_remarks)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_response))
    application.add_handler(CommandHandler("balance", check_balance))

    # Start bot
    application.run_polling()

if __name__ == '__main__':
    main()