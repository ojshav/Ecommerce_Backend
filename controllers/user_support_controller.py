# controllers/user/user_support_controller.py
from flask import current_app
from common.database import db
from models.support_ticket_model import SupportTicket, SupportTicketMessage
from auth.models import User, MerchantProfile # MerchantProfile to check if user is also a merchant
from models.enums import TicketStatus, TicketPriority, TicketCreatorRole
from werkzeug.exceptions import NotFound, Forbidden, BadRequest
from sqlalchemy import desc, asc
import datetime
from services.s3_service import get_s3_service


def _upload_support_attachment(file_to_upload, folder_name="support_attachments"):
    if not file_to_upload:
        return None
    try:
        s3_service = get_s3_service()
        upload_result = s3_service.upload_support_attachment(file_to_upload, folder_name)
        return upload_result.get('url')
    except Exception as e:
        current_app.logger.error(f"S3 upload failed for support attachment: {e}")
        raise Exception(f"File upload failed: {str(e)}")


class UserSupportTicketController:

    @staticmethod
    def create_ticket(data, creator_user_id, image_file=None):
        title = data.get('title')
        description = data.get('description')
        priority_str = data.get('priority', TicketPriority.MEDIUM.value).lower()
        related_order_id = data.get('related_order_id')
        related_product_id = data.get('related_product_id')
        if related_product_id:
            try:
                related_product_id = int(related_product_id)
            except ValueError:
                raise BadRequest("Invalid related_product_id format.")


        if not title or not description:
            raise BadRequest("Title and description are required.")

        try:
            priority_enum_val = TicketPriority(priority_str)
        except ValueError:
            raise BadRequest(f"Invalid priority value. Choose from: {[p.value for p in TicketPriority]}")

        image_url = None
        if image_file:
            try:
                image_url = _upload_support_attachment(image_file, "user_support_tickets")
            except Exception as e:
                current_app.logger.error(f"Failed to upload image for user support ticket: {e}")
                # Decide if this should fail the ticket creation or proceed without image
                # For now, proceeding without image but logging error

        user = User.query.get_or_404(creator_user_id)
        
        # For tickets created through this controller, assume creator_role is CUSTOMER
        # If a user is also a merchant and wants to create a merchant-specific ticket,
        # they should use the merchant portal's support section.
        creator_role_val = TicketCreatorRole.CUSTOMER.value
        merchant_id_for_ticket = None

        # Optional: If a user is *also* a merchant, and the ticket is about their store,
        # you might allow them to specify this, or infer it.
        # For simplicity, tickets via this user controller are primarily customer-centric.
        # If they have a merchant profile, it COULD be linked if 'acting_as_merchant' flag is sent.
        # acting_as_merchant = data.get('acting_as_merchant', False)
        # if acting_as_merchant:
        #    merchant_profile = MerchantProfile.query.filter_by(user_id=creator_user_id).first()
        #    if merchant_profile:
        #        creator_role_val = TicketCreatorRole.MERCHANT.value
        #        merchant_id_for_ticket = merchant_profile.id


        new_ticket = SupportTicket(
            creator_user_id=creator_user_id,
            creator_role=creator_role_val, 
            merchant_id=merchant_id_for_ticket, # Typically None for customer tickets
            title=title,
            description=description,
            image_url=image_url,
            priority=priority_enum_val.value,
            status=TicketStatus.OPEN.value,
            related_order_id=related_order_id,
            related_product_id=related_product_id,
            updated_at = datetime.datetime.utcnow() # Explicitly set initial updated_at
        )
        db.session.add(new_ticket)
        db.session.flush() # Flush to get new_ticket.id for the message

        # Create the initial message from the description
        initial_message = SupportTicketMessage(
            ticket_id=new_ticket.id,
            sender_user_id=creator_user_id, 
            message_text=f"Initial problem description:\n{description}"
        )
        db.session.add(initial_message)
        db.session.commit()
        return new_ticket

    @staticmethod
    def list_user_tickets(creator_user_id, status_filter=None, sort_by=None, page=1, per_page=10):
        query = SupportTicket.query.filter_by(creator_user_id=creator_user_id)

        if status_filter and status_filter.lower() != 'all':
            try:
                status_enum_val = TicketStatus(status_filter.lower()).value
                query = query.filter_by(status=status_enum_val)
            except ValueError:
                current_app.logger.warning(f"Invalid status filter value for user tickets: {status_filter}")
                pass # Or raise BadRequest

        if sort_by:
            sort_order_func = desc if sort_by.startswith('-') else asc
            sort_field_name = sort_by.lstrip('-')
            if hasattr(SupportTicket, sort_field_name):
                sort_field = getattr(SupportTicket, sort_field_name)
                query = query.order_by(sort_order_func(sort_field))
            else: # Default sort
                query = query.order_by(desc(SupportTicket.updated_at))
        else: # Default sort if not specified
            query = query.order_by(desc(SupportTicket.updated_at))
            
        paginated_tickets = query.paginate(page=page, per_page=per_page, error_out=False)
        return paginated_tickets

    @staticmethod
    def get_user_ticket_details(ticket_uid, creator_user_id):
        ticket = SupportTicket.query.filter_by(ticket_uid=ticket_uid, creator_user_id=creator_user_id).first()
        if not ticket:
            raise NotFound("Support ticket not found or you do not have permission to view it.")
        return ticket

    @staticmethod
    def add_message_to_ticket_by_user(ticket_uid, creator_user_id, message_text, attachment_file=None):
        ticket = SupportTicket.query.filter_by(ticket_uid=ticket_uid, creator_user_id=creator_user_id).first()
        if not ticket:
            raise NotFound("Support ticket not found or you do not have permission to add a message.")

        if ticket.status == TicketStatus.CLOSED.value:
            raise BadRequest("Cannot add messages to a closed ticket.")
        
        if not message_text and not attachment_file:
            raise BadRequest("Message text or an attachment is required.")

        attachment_url = None
        if attachment_file:
            try:
                attachment_url = _upload_support_attachment(attachment_file, "user_support_attachments")
            except Exception as e:
                 current_app.logger.error(f"Failed to upload attachment for user support ticket message: {e}")
                 # Decide if this should fail or proceed without attachment

        new_message = SupportTicketMessage(
            ticket_id=ticket.id,
            sender_user_id=creator_user_id, # The user themself is the sender
            message_text=message_text or "", # Ensure message_text is not None
            attachment_url=attachment_url
        )
        db.session.add(new_message)
        
        # If admin had set it to AWAITING_CUSTOMER_REPLY, or if it was RESOLVED,
        # user's reply should bring it back to IN_PROGRESS (or OPEN if no admin has touched it yet)
        if ticket.status == TicketStatus.AWAITING_CUSTOMER.value:
            ticket.status = TicketStatus.IN_PROGRESS.value
        elif ticket.status == TicketStatus.RESOLVED.value:
             ticket.status = TicketStatus.IN_PROGRESS.value # Re-open if user replies to resolved ticket
        elif ticket.status == TicketStatus.OPEN.value and ticket.assigned_to_admin_id is None:
            pass # Stays OPEN if no admin assigned yet
        else: # Any other status (like OPEN with admin assigned, or IN_PROGRESS)
            ticket.status = TicketStatus.IN_PROGRESS.value

        ticket.updated_at = datetime.datetime.utcnow()
        db.session.commit()
        return new_message

    @staticmethod
    def close_resolved_ticket_by_user(ticket_uid, creator_user_id):
        ticket = SupportTicket.query.filter_by(ticket_uid=ticket_uid, creator_user_id=creator_user_id).first()
        if not ticket:
            raise NotFound("Support ticket not found or access denied.")

        if ticket.status != TicketStatus.RESOLVED.value:
            raise BadRequest("Only tickets marked as 'Resolved' by support can be closed by the user.")

        ticket.status = TicketStatus.CLOSED.value
        ticket.resolved_at = datetime.datetime.utcnow()
        ticket.updated_at = datetime.datetime.utcnow()
        db.session.commit()
        return ticket