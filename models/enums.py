from enum import Enum

class MediaType(Enum):
    IMAGE = 'image'
    VIDEO = 'video'

class DiscountType(Enum):
    PERCENTAGE = 'percentage'
    FIXED = 'fixed'

class AttributeInputType(Enum):
    TEXT = 'text'
    NUMBER = 'number'
    SELECT = 'select'
    MULTISELECT = 'multiselect'
    BOOLEAN = 'boolean'

class BrandRequestStatus(Enum):
    PENDING = 'pending'
    APPROVED = 'approved'
    REJECTED = 'rejected'

class PlacementTypeEnum(Enum):
    FEATURED = "featured"
    PROMOTED = "promoted"
    


class AddressTypeEnum(Enum):
    SHIPPING = "shipping"
    BILLING = "billing"
    BOTH = "both"

class OrderStatusEnum(Enum):
    PENDING_PAYMENT = "pending_payment"
    AWAITING_FULFILLMENT = "awaiting_fulfillment" # Alias for PROCESSING, or more specific
    PROCESSING = "processing"
    PENDING_SHIPMENT = "pending_shipment"
    SHIPPED = "shipped"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED_BY_CUSTOMER = "cancelled_by_customer"
    CANCELLED_BY_MERCHANT = "cancelled_by_merchant"
    CANCELLED_BY_ADMIN = "cancelled_by_admin"
    REFUND_REQUESTED = "refund_requested" # Different from RETURN_REQUESTED if refund is for non-delivery etc.
    REFUND_PROCESSING = "refund_processing"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    RETURN_REQUESTED = "return_requested"
    RETURN_APPROVED = "return_approved"
    RETURN_REJECTED = "return_rejected"
    RETURN_RECEIVED = "return_received" # Physical items received back
    RETURN_COMPLETED = "return_completed" # Return processed, refund issued if applicable

class PaymentMethodEnum(Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    NET_BANKING = "net_banking"
    UPI = "upi"
    WALLET = "wallet"
    COD = "cash_on_delivery"
    BANK_TRANSFER = "bank_transfer"
    PAYPAL = "paypal"
    STRIPE = "stripe"
    OTHER = "other"

class PaymentStatusEnum(Enum):
    PENDING = "pending"
    AWAITING_CAPTURE = "awaiting_capture" # Authorized, not yet captured
    SUCCESSFUL = "successful" # Or CAPTURED
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    EXPIRED = "expired" # e.g. payment link expired

class ShipmentStatusEnum(Enum):
    PENDING_PICKUP = "pending_pickup"
    LABEL_CREATED = "label_created"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELIVERY_ATTEMPTED = "delivery_attempted" # Failed delivery attempt
    EXCEPTION = "exception" # Other carrier exceptions
    RETURN_TO_SENDER = "return_to_sender"
    CANCELLED = "cancelled"

class OrderItemStatusEnum(Enum): # Status per line item, useful in multi-merchant
    PENDING_FULFILLMENT = "pending_fulfillment"
    PROCESSING = "processing"
    READY_TO_SHIP = "ready_to_ship"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURN_REQUESTED = "return_requested"
    RETURN_APPROVED = "return_approved"
    RETURN_REJECTED = "return_rejected"
    RETURNED = "returned"
    REFUNDED = "refunded"

class CardTypeEnum(Enum):
    CREDIT = 'credit'
    DEBIT = 'debit'

class CardStatusEnum(Enum):
    ACTIVE = 'active'
    EXPIRED = 'expired'
    SUSPENDED = 'suspended'
    DELETED = 'deleted'





class TicketPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @classmethod
    def choices(cls):
        return [(choice.name, choice.value) for choice in cls]

    @classmethod
    def coerce(cls, item):
        return cls(item) if not isinstance(item, cls) else item

    def __str__(self):
        return self.value

class TicketStatus(Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    AWAITING_CUSTOMER = "awaiting_customer_reply" 
    AWAITING_MERCHANT = "awaiting_merchant_reply" 
    RESOLVED = "resolved"
    CLOSED = "closed"

    @classmethod
    def choices(cls):
        return [(choice.name, choice.value) for choice in cls]

    @classmethod
    def coerce(cls, item):
        return cls(item) if not isinstance(item, cls) else item

    def __str__(self):
        return self.value
    

class TicketCreatorRole(Enum): 
    CUSTOMER = "customer"
    MERCHANT = "merchant"


# Enum for GST Price Conditions
class ProductPriceConditionType(Enum):
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL_TO = "less_than_or_equal_to"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL_TO = "greater_than_or_equal_to"
    EQUAL_TO = "equal_to"
    ANY = "any" # Represents no price condition

class StreamStatus(Enum):
    scheduled = 'scheduled'
    LIVE = 'live'
    ENDED = 'ended'
    CANCELLED = 'cancelled'

