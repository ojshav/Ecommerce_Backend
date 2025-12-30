from flask import current_app
from common.database import db
from models.support_ticket_model import SupportTicket, SupportTicketMessage 
from auth.models import User, MerchantProfile 
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


class MerchantSupportTicketController:

    @staticmethod
    def create_ticket(data, merchant_id, creator_user_id, image_file=None): 
        title = data.get('title')
        description = data.get('description')
        priority_str = data.get('priority', TicketPriority.MEDIUM.value).lower() 
        related_order_id = data.get('related_order_id') # Optional
        raw_related_product_id = data.get('related_product_id')
        related_product_id = None

        if raw_related_product_id is not None:
            try:
                related_product_id = int(raw_related_product_id)
            except (ValueError, TypeError):
                raise BadRequest("related_product_id must be an integer.")

        if not title or not description:
            raise BadRequest("Title and description are required.")

        try:
            priority_enum_val = TicketPriority(priority_str)
        except ValueError:
            raise BadRequest(f"Invalid priority value. Choose from: {[p.value for p in TicketPriority]}")
        
        image_url = None
        if image_file:
            try:
                image_url = _upload_support_attachment(image_file, "support_tickets")
            except Exception as e:
                current_app.logger.error(f"Failed to upload image for support ticket: {e}")
                # Proceeding without image but logging error

        new_ticket = SupportTicket(
            creator_user_id=creator_user_id, # Set the creator user
            creator_role=TicketCreatorRole.MERCHANT.value, # Explicitly set role
            merchant_id=merchant_id, # Link to merchant profile
            title=title,
            description=description,
            image_url=image_url,
            priority=priority_enum_val.value,
            status=TicketStatus.OPEN.value,
            related_order_id=related_order_id,
            related_product_id=related_product_id,
            updated_at = datetime.datetime.utcnow() 
        )
        db.session.add(new_ticket)
        db.session.flush() 

        initial_message = SupportTicketMessage(
            ticket_id=new_ticket.id,
            sender_user_id=creator_user_id, 
            message_text=f"Initial problem description:\n{description}"
        )
        db.session.add(initial_message)
        db.session.commit()
        return new_ticket

    @staticmethod
    def list_merchant_tickets(merchant_id, status_filter=None, sort_by=None, page=1, per_page=10):
        # This lists tickets where the merchant_id matches, regardless of who (which user under the merchant) created it,
        # or if the creator_role was 'MERCHANT'
        query = SupportTicket.query.filter_by(merchant_id=merchant_id)

        if status_filter and status_filter.lower() != 'all':
            try:
                status_enum_val = TicketStatus(status_filter.lower()).value
                query = query.filter_by(status=status_enum_val)
            except ValueError:
                # It's better to log and ignore or return empty than raise BadRequest for a filter
                current_app.logger.warning(f"Invalid status filter value received: {status_filter}")
                # Optionally, you could raise BadRequest("Invalid status filter value.")
                pass


        if sort_by:
            sort_order_func = desc if sort_by.startswith('-') else asc
            sort_field_name = sort_by.lstrip('-')
            if hasattr(SupportTicket, sort_field_name):
                sort_field = getattr(SupportTicket, sort_field_name)
                query = query.order_by(sort_order_func(sort_field))
            else: 
                query = query.order_by(desc(SupportTicket.updated_at))
        else: 
            query = query.order_by(desc(SupportTicket.updated_at))

        paginated_tickets = query.paginate(page=page, per_page=per_page, error_out=False)
        return paginated_tickets

    @staticmethod
    def get_merchant_ticket_details(ticket_uid, merchant_id):
        # Ensures the ticket belongs to the requesting merchant
        ticket = SupportTicket.query.filter_by(ticket_uid=ticket_uid, merchant_id=merchant_id).first()
        if not ticket:
            raise NotFound("Support ticket not found or access denied.")
        return ticket

    @staticmethod
    def add_message_to_ticket(ticket_uid, merchant_id, sender_user_id, message_text, attachment_file=None):
        # Ensure the ticket belongs to the merchant adding the message
        ticket = SupportTicket.query.filter_by(ticket_uid=ticket_uid, merchant_id=merchant_id).first()
        if not ticket:
            raise NotFound("Support ticket not found or access denied.")

        if ticket.status == TicketStatus.CLOSED.value:
            raise BadRequest("Cannot add messages to a closed ticket.")
        
        if not message_text and not attachment_file: 
            raise BadRequest("Message text or an attachment is required.")

        attachment_url = None
        if attachment_file:
            try:
                attachment_url = _upload_support_attachment(attachment_file, "support_attachments")
            except Exception as e:
                current_app.logger.error(f"Failed to upload attachment for support ticket message: {e}")
                # Decide if this should be a hard fail or proceed without attachment

        new_message = SupportTicketMessage(
            ticket_id=ticket.id,
            sender_user_id=sender_user_id, 
            message_text=message_text or "", 
            attachment_url=attachment_url
        )
        db.session.add(new_message)
        
        # If admin had set it to AWAITING_MERCHANT_REPLY, or if it was RESOLVED,
        # merchant's reply should bring it back to IN_PROGRESS
        if ticket.status in [TicketStatus.RESOLVED.value, TicketStatus.AWAITING_MERCHANT.value]:
            ticket.status = TicketStatus.IN_PROGRESS.value
        
        ticket.updated_at = datetime.datetime.utcnow() 
        db.session.commit()
        return new_message

    @staticmethod
    def close_resolved_ticket(ticket_uid, merchant_id):
        ticket = SupportTicket.query.filter_by(ticket_uid=ticket_uid, merchant_id=merchant_id).first()
        if not ticket:
            raise NotFound("Support ticket not found or access denied.")

        if ticket.status != TicketStatus.RESOLVED.value:
            raise BadRequest("Only resolved tickets can be closed by the merchant.")

        ticket.status = TicketStatus.CLOSED.value
        ticket.resolved_at = datetime.datetime.utcnow() 
        ticket.updated_at = datetime.datetime.utcnow() 
        db.session.commit()
        return ticket