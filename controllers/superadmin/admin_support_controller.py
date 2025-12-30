from flask import current_app
from common.database import db
from models.support_ticket_model import SupportTicket, SupportTicketMessage 
from auth.models import User, MerchantProfile 
from models.enums import TicketStatus, TicketPriority, TicketCreatorRole 
from werkzeug.exceptions import NotFound, Forbidden, BadRequest
from sqlalchemy import desc, asc, or_
from sqlalchemy.orm import joinedload, selectinload 
import datetime
from services.s3_service import get_s3_service

def _upload_support_attachment(file_to_upload, folder_name="support_attachments"):
    if not file_to_upload:
        return None
    try:
        s3_service = get_s3_service()
        upload_result = s3_service.upload_support_attachment(file_to_upload, folder_name)
        current_app.logger.info(f"S3 upload successful: {upload_result.get('url')}")
        return upload_result.get('url')
    except Exception as e:
        current_app.logger.error(f"S3 upload failed: {str(e)}")
        raise Exception(f"File upload failed: {str(e)}")


class AdminSupportTicketController:

    @staticmethod
    def list_all_tickets(status_filter=None, priority_filter=None, creator_role_filter=None,
                         assigned_to_filter=None, sort_by=None, search_query=None, 
                         page=1, per_page=10):
        
        query = SupportTicket.query.options(
            joinedload(SupportTicket.creator).load_only(User.id, User.first_name, User.last_name, User.email), # Load only necessary fields
            joinedload(SupportTicket.merchant).load_only(MerchantProfile.id, MerchantProfile.business_name),
            joinedload(SupportTicket.assigned_admin).load_only(User.id, User.first_name, User.last_name, User.email)
        )

        # Explicit joins needed for filtering/searching on related tables if not covered by options() for that purpose
        # The options() above are mainly for optimizing the SELECT part for serialization later.
        # For filtering/searching, explicit joins .
        query = query.join(User, SupportTicket.creator_user_id == User.id)
        query = query.outerjoin(MerchantProfile, SupportTicket.merchant_id == MerchantProfile.id)


        if status_filter and status_filter.lower() != 'all':
            try:
                status_enum_val = TicketStatus(status_filter.lower()).value
                query = query.filter(SupportTicket.status == status_enum_val)
            except ValueError:
                current_app.logger.warning(f"Admin: Invalid status filter: {status_filter}")
                pass 

        if priority_filter and priority_filter.lower() != 'all':
            try:
                priority_enum_val = TicketPriority(priority_filter.lower()).value
                query = query.filter(SupportTicket.priority == priority_enum_val)
            except ValueError:
                current_app.logger.warning(f"Admin: Invalid priority filter: {priority_filter}")
                pass
        
        if creator_role_filter and creator_role_filter.lower() != 'all':
            try:
                role_enum_val = TicketCreatorRole(creator_role_filter.lower()).value
                query = query.filter(SupportTicket.creator_role == role_enum_val)
            except ValueError:
                 current_app.logger.warning(f"Admin: Invalid creator_role filter: {creator_role_filter}")
                 pass

        if assigned_to_filter:
            if assigned_to_filter.lower() == 'unassigned':
                query = query.filter(SupportTicket.assigned_to_admin_id.is_(None))
            elif assigned_to_filter.isdigit():
                query = query.filter(SupportTicket.assigned_to_admin_id == int(assigned_to_filter))
        
        if search_query:
            search_ilike = f"%{search_query}%"
            search_conditions = [
                SupportTicket.ticket_uid.ilike(search_ilike),
                SupportTicket.title.ilike(search_ilike),
                SupportTicket.description.ilike(search_ilike),
                User.email.ilike(search_ilike), 
                (User.first_name + " " + User.last_name).ilike(search_ilike), 
                MerchantProfile.business_name.ilike(search_ilike) 
            ]
            query = query.filter(or_(*search_conditions))

        if sort_by:
            sort_order_func = desc if sort_by.startswith('-') else asc
            sort_field_name = sort_by.lstrip('-')

            if sort_field_name == "creator_name":
                query = query.order_by(sort_order_func(User.first_name), sort_order_func(User.last_name))
            elif sort_field_name == "merchant_name":
                 query = query.order_by(sort_order_func(MerchantProfile.business_name))
            elif sort_field_name == "assigned_admin_name":
                AssignedAdminUser = db.aliased(User, name="assigned_admin_user_for_sort") 
                query = query.outerjoin(AssignedAdminUser, SupportTicket.assigned_to_admin_id == AssignedAdminUser.id)
                query = query.order_by(sort_order_func(AssignedAdminUser.first_name), sort_order_func(AssignedAdminUser.last_name))
            elif hasattr(SupportTicket, sort_field_name):
                sort_field = getattr(SupportTicket, sort_field_name)
                query = query.order_by(sort_order_func(sort_field))
            else: 
                current_app.logger.warning(f"Admin: Invalid sort_by field: {sort_field_name}, defaulting to -updated_at")
                query = query.order_by(desc(SupportTicket.updated_at))
        else: 
            query = query.order_by(desc(SupportTicket.updated_at))
            
        paginated_tickets = query.paginate(page=page, per_page=per_page, error_out=False)
        return paginated_tickets

   

    @staticmethod
    def get_ticket_details_for_admin(ticket_uid):
        # Cannot directly joinedload messages.sender if messages is lazy='dynamic'
        ticket = SupportTicket.query.options(
            joinedload(SupportTicket.creator).load_only(User.id, User.first_name, User.last_name, User.email, User.role),
            joinedload(SupportTicket.merchant).load_only(MerchantProfile.id, MerchantProfile.business_name),
            joinedload(SupportTicket.assigned_admin).load_only(User.id, User.first_name, User.last_name, User.email),
           
        ).filter_by(ticket_uid=ticket_uid).first()
        
        if not ticket:
            raise NotFound(f"Support ticket with UID '{ticket_uid}' not found.")
        # Sender for messages will be handled during ticket.serialize()
        return ticket

    @staticmethod
    def assign_ticket_to_admin(ticket_uid, admin_user_id_to_assign, current_admin_id_performing_action):
        ticket = SupportTicket.query.filter_by(ticket_uid=ticket_uid).first_or_404(
            description=f"Support ticket UID '{ticket_uid}' not found for assignment."
        )
        
        try:
            admin_id_int = int(admin_user_id_to_assign)
        except ValueError:
            raise BadRequest("Admin ID for assignment must be an integer.")

        admin_user_to_be_assigned = User.query.get(admin_id_int)
        if not admin_user_to_be_assigned:
            raise BadRequest(f"Admin user with ID '{admin_id_int}' to assign not found.")
            
        admin_roles = ['ADMIN', 'SUPERADMIN', 'SUPPORT'] 
        user_role_name = ""
        # Ensure role attribute exists and is accessed correctly
        if hasattr(admin_user_to_be_assigned, 'role') and admin_user_to_be_assigned.role:
            if hasattr(admin_user_to_be_assigned.role, 'name'): 
                user_role_name = admin_user_to_be_assigned.role.name.upper()
            elif isinstance(admin_user_to_be_assigned.role, str): 
                user_role_name = admin_user_to_be_assigned.role.upper()
        
        if user_role_name not in admin_roles:
            raise BadRequest("The selected user does not have permission to be assigned tickets (not an admin/support role).")

        ticket.assigned_to_admin_id = admin_id_int
        if ticket.status == TicketStatus.OPEN.value:
            ticket.status = TicketStatus.IN_PROGRESS.value
        
        ticket.updated_at = datetime.datetime.utcnow()
        
        assigned_by_admin = User.query.get(current_admin_id_performing_action)
        assigned_by_name = f"{assigned_by_admin.first_name} {assigned_by_admin.last_name}".strip() if assigned_by_admin else "System Action"

        assignment_message_text = f"Ticket assigned to {admin_user_to_be_assigned.first_name or ''} {admin_user_to_be_assigned.last_name or ''} (ID: {admin_user_to_be_assigned.id}) by {assigned_by_name}."
        assignment_message = SupportTicketMessage(
            ticket_id=ticket.id,
            sender_user_id=current_admin_id_performing_action,
            message_text=assignment_message_text.strip()
        )
        db.session.add(assignment_message)
        db.session.commit()
        return ticket

    @staticmethod
    def admin_reply_to_ticket(ticket_uid, admin_user_id, message_text, attachment_file=None):
        ticket = SupportTicket.query.filter_by(ticket_uid=ticket_uid).first_or_404(
            description=f"Support ticket UID '{ticket_uid}' not found."
        )

        if ticket.status == TicketStatus.CLOSED.value:
            raise BadRequest("Cannot reply to a closed ticket.")
            
        if not (message_text and message_text.strip()) and not attachment_file:
            raise BadRequest("Message text or an attachment is required.")

        attachment_url = None
        if attachment_file:
            try:
                attachment_url = _upload_support_attachment(attachment_file, "admin_support_attachments")
            except Exception as e:
                current_app.logger.error(f"Admin: Failed to upload attachment for support message to ticket {ticket_uid}: {e}")
                raise BadRequest(f"Attachment upload failed: {str(e)}")

        new_message = SupportTicketMessage(
            ticket_id=ticket.id,
            sender_user_id=admin_user_id,
            message_text=message_text.strip() if message_text else "",
            attachment_url=attachment_url
        )
        db.session.add(new_message)
        
        try:
            creator_role_enum = TicketCreatorRole(ticket.creator_role) 
            if creator_role_enum == TicketCreatorRole.CUSTOMER:
                ticket.status = TicketStatus.AWAITING_CUSTOMER.value
            elif creator_role_enum == TicketCreatorRole.MERCHANT:
                ticket.status = TicketStatus.AWAITING_MERCHANT.value
            else: 
                ticket.status = TicketStatus.IN_PROGRESS.value
        except ValueError:
            current_app.logger.error(f"Invalid creator_role '{ticket.creator_role}' found for ticket {ticket.ticket_uid}")
            ticket.status = TicketStatus.IN_PROGRESS.value # Fallback
            
        ticket.updated_at = datetime.datetime.utcnow()
        db.session.commit()
        return new_message

    @staticmethod
    def update_ticket_status(ticket_uid, new_status_str, admin_user_id, notes=None):
        ticket = SupportTicket.query.filter_by(ticket_uid=ticket_uid).first_or_404(
            description=f"Support ticket UID '{ticket_uid}' not found."
        )
        
        try:
            new_status_enum = TicketStatus(new_status_str.lower())
        except ValueError:
            raise BadRequest(f"Invalid status value: '{new_status_str}'. Choose from: {[s.value for s in TicketStatus]}")

        old_status_display = ticket.status.replace('_',' ').title()
        ticket.status = new_status_enum.value
        
        if new_status_enum in [TicketStatus.RESOLVED, TicketStatus.CLOSED] and not ticket.resolved_at:
            ticket.resolved_at = datetime.datetime.utcnow()
        elif new_status_enum not in [TicketStatus.RESOLVED, TicketStatus.CLOSED] and ticket.resolved_at:
            ticket.resolved_at = None 

        ticket.updated_at = datetime.datetime.utcnow()

        status_change_message_text = f"Ticket status changed from {old_status_display} to {new_status_enum.value.replace('_',' ').title()} by admin."
        if notes and notes.strip():
            status_change_message_text += f"\nAdmin Notes: {notes.strip()}"
        
        status_update_message = SupportTicketMessage(
            ticket_id=ticket.id,
            sender_user_id=admin_user_id,
            message_text=status_change_message_text
        )
        db.session.add(status_update_message)
        db.session.commit()
        return ticket

    @staticmethod
    def update_ticket_priority(ticket_uid, new_priority_str, admin_user_id):
        ticket = SupportTicket.query.filter_by(ticket_uid=ticket_uid).first_or_404(
            description=f"Support ticket UID '{ticket_uid}' not found."
        )
        
        try:
            new_priority_enum = TicketPriority(new_priority_str.lower())
        except ValueError:
            raise BadRequest(f"Invalid priority value: '{new_priority_str}'. Choose from: {[p.value for p in TicketPriority]}")

        old_priority_display = ticket.priority.title()
        ticket.priority = new_priority_enum.value
        ticket.updated_at = datetime.datetime.utcnow()

        priority_change_message = SupportTicketMessage(
            ticket_id=ticket.id,
            sender_user_id=admin_user_id, 
            message_text=f"Ticket priority changed from {old_priority_display} to {new_priority_enum.value.title()} by admin."
        )
        db.session.add(priority_change_message)
        db.session.commit()
        return ticket