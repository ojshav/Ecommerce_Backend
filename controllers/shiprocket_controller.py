import requests
import json
import os
from datetime import datetime, timezone, timedelta
from flask import current_app
from common.database import db
from models.order import Order, OrderItem
from models.user_address import UserAddress
from models.product import Product
from models.shipment import Shipment
from auth.models.models import User, MerchantProfile
from models.enums import ShipmentStatusEnum
from decimal import Decimal
from urllib.parse import urlencode

class ShipRocketController:
    """Controller for ShipRocket shipping integration"""
    
    BASE_URL = "https://apiv2.shiprocket.in/v1/external"
    
    def __init__(self):
        self.email = os.getenv('SHIPROCKET_EMAIL')
        self.password = os.getenv('SHIPROCKET_PASSWORD')
        self.token = None
        self.token_expiry = None
    
    def _get_auth_token(self):
        """Get authentication token from ShipRocket"""
        try:
            if self.token and self.token_expiry and datetime.now(timezone.utc) < self.token_expiry:
                return self.token
            
            url = f"{self.BASE_URL}/auth/login"
            payload = {
                "email": self.email,
                "password": self.password
            }
            
            response = requests.post(url, json=payload)
            response.raise_for_status()
            
            data = response.json()
            self.token = data.get('token')
            # Token typically expires in 24 h. Use timedelta to avoid hour overflow.
            self.token_expiry = datetime.now(timezone.utc) + timedelta(hours=23)
            
            return self.token
            
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"ShipRocket authentication failed: {str(e)}")
            raise Exception("Failed to authenticate with ShipRocket")
    
    def _make_request(self, method, endpoint, data=None, params=None):
        """Make authenticated request to ShipRocket API"""
        try:
            token = self._get_auth_token()
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            url = f"{self.BASE_URL}/{endpoint}"
            
            current_app.logger.info(f"Making {method} request to {url}")
            if params:
                current_app.logger.info(f"Request params: {params}")
            if data:
                current_app.logger.info(f"Request data: {data}")
            
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Log response status only, not the full content
            current_app.logger.info(f"ShipRocket API response status: {response.status_code}")
            
            if response.status_code >= 400:
                error_content = response.text
                current_app.logger.error(f"ShipRocket API error response: {error_content}")
                raise requests.exceptions.HTTPError(f"{response.status_code} {response.reason}: {error_content}")
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"ShipRocket API request failed: {str(e)}")
            raise Exception(f"ShipRocket API request failed: {str(e)}")
    
    def _clean_courier_data(self, courier):
        """Clean up courier data to return only essential information"""
        return {
            'courier_company_id': courier.get('courier_company_id'),
            'courier_name': courier.get('courier_name'),
            'rate': courier.get('rate'),
            'estimated_delivery_days': courier.get('estimated_delivery_days'),
            'rating': courier.get('rating'),
            'freight_charge': courier.get('freight_charge'),
            'cod_charges': courier.get('cod_charges', 0)
        }
    
    def _format_phone_number(self, phone):
        """
        Format phone number for ShipRocket API (convert to integer)
        
        Args:
            phone (str): Phone number string
            
        Returns:
            int: Formatted phone number as integer, or 0 if invalid
        """
        if not phone:
            return 0
        
        try:
            # Remove all non-digit characters
            cleaned_phone = ''.join(filter(str.isdigit, str(phone)))
            
            # Check if it's a valid phone number (at least 10 digits)
            if len(cleaned_phone) >= 10:
                return int(cleaned_phone)
            else:
                current_app.logger.warning(f"Invalid phone number format: {phone}")
                return 0
        except (ValueError, TypeError) as e:
            current_app.logger.warning(f"Error formatting phone number {phone}: {str(e)}")
            return 0
    
    def check_serviceability(self, pickup_pincode, delivery_pincode, weight, cod=0, order_id=None):
        """
        Check courier serviceability and get shipping charges
        
        Args:
            pickup_pincode (str): Pickup location pincode
            delivery_pincode (str): Delivery location pincode
            weight (float): Package weight in kg
            cod (int): Cash on delivery amount (0 for prepaid)
            order_id (str): Order ID for the request (optional, not used for serviceability checks)
        
        Returns:
            dict: Serviceability response with available couriers and charges
        """
        try:
            # Validate and format parameters
            if not pickup_pincode or not delivery_pincode:
                raise Exception("Pickup and delivery pincodes are required")
            
            # Ensure pincodes are strings and valid
            pickup_pincode = str(pickup_pincode).strip()
            delivery_pincode = str(delivery_pincode).strip()
            
            if len(pickup_pincode) != 6 or len(delivery_pincode) != 6:
                raise Exception("Pincodes must be 6 digits")
            
            # Validate weight
            if weight <= 0 or weight > 50:  # ShipRocket typically has weight limits
                raise Exception("Weight must be between 0.1 and 50 kg")
            
            # Convert COD amount to boolean and separate amount
            cod_amount = float(cod) if cod else 0
            is_cod = cod_amount > 0  # True if COD amount > 0, False for prepaid
            
            # Try different approaches for ShipRocket API
            # First attempt: Basic GET request without cod parameter for prepaid
            if not is_cod:
                params = {
                    'pickup_postcode': pickup_pincode,
                    'delivery_postcode': delivery_pincode,
                    'weight': round(weight, 2),
                }
                
                # Don't include order_id for serviceability checks as it's not needed
                # and causes "Order doesn't exist" errors
                
                current_app.logger.info(f"ShipRocket serviceability GET request (prepaid): {params}")
                
                try:
                    response = self._make_request('GET', 'courier/serviceability/', params=params)
                    
                    # Log only essential information instead of full response
                    if response.get('data', {}).get('available_courier_companies'):
                        couriers_count = len(response['data']['available_courier_companies'])
                        current_app.logger.info(f"ShipRocket serviceability successful: {couriers_count} couriers available")
                        
                        # Clean up the response to return only essential courier information
                        cleaned_couriers = [self._clean_courier_data(courier) for courier in response['data']['available_courier_companies']]
                        response['data']['available_courier_companies'] = cleaned_couriers
                    else:
                        current_app.logger.info("ShipRocket serviceability response: No couriers available")
                        response['data']['available_courier_companies'] = []
                    
                    return response
                except Exception as first_error:
                    current_app.logger.warning(f"Prepaid GET attempt failed: {str(first_error)}")
            
            # Second attempt: GET with cod parameter as integer (1 for COD, 0 for prepaid)
            params = {
                'pickup_postcode': pickup_pincode,
                'delivery_postcode': delivery_pincode,
                'weight': round(weight, 2),
                'cod': 1 if is_cod else 0,  # Try integer format
            }
            
            # Add COD amount if it's a COD order
            if is_cod:
                params['cod_amount'] = int(cod_amount)
            
            # Don't include order_id for serviceability checks
            
            current_app.logger.info(f"ShipRocket serviceability GET request (with cod int): {params}")
            
            try:
                response = self._make_request('GET', 'courier/serviceability/', params=params)
                
                # Log only essential information instead of full response
                if response.get('data', {}).get('available_courier_companies'):
                    couriers_count = len(response['data']['available_courier_companies'])
                    current_app.logger.info(f"ShipRocket serviceability successful: {couriers_count} couriers available")
                    
                    # Clean up the response to return only essential courier information
                    cleaned_couriers = [self._clean_courier_data(courier) for courier in response['data']['available_courier_companies']]
                    response['data']['available_courier_companies'] = cleaned_couriers
                else:
                    current_app.logger.info("ShipRocket serviceability response: No couriers available")
                    response['data']['available_courier_companies'] = []
                
                return response
            except Exception as second_error:
                current_app.logger.warning(f"GET with cod int failed: {str(second_error)}")
                
                # Third attempt: GET with cod parameter as string
                params = {
                    'pickup_postcode': pickup_pincode,
                    'delivery_postcode': delivery_pincode,
                    'weight': round(weight, 2),
                    'cod': 'true' if is_cod else 'false',  # String format
                }
                
                # Add COD amount if it's a COD order
                if is_cod:
                    params['cod_amount'] = int(cod_amount)
                
                # Don't include order_id for serviceability checks
                
                current_app.logger.info(f"ShipRocket serviceability GET request (with cod string): {params}")
                
                response = self._make_request('GET', 'courier/serviceability/', params=params)
                
                # Log only essential information instead of full response
                if response.get('data', {}).get('available_courier_companies'):
                    couriers_count = len(response['data']['available_courier_companies'])
                    current_app.logger.info(f"ShipRocket serviceability successful: {couriers_count} couriers available")
                    
                    # Clean up the response to return only essential courier information
                    cleaned_couriers = [self._clean_courier_data(courier) for courier in response['data']['available_courier_companies']]
                    response['data']['available_courier_companies'] = cleaned_couriers
                else:
                    current_app.logger.info("ShipRocket serviceability response: No couriers available")
                    response['data']['available_courier_companies'] = []
                
                return response
            
        except Exception as e:
            current_app.logger.error(f"Serviceability check failed: {str(e)}")
            return {'data': {'available_courier_companies': []}, 'message': str(e)}
    
    def create_order(self, order_data):
        """
        Create order in ShipRocket
        
        Args:
            order_data (dict): Order data for ShipRocket
        
        Returns:
            dict: ShipRocket order response with order_id and shipment_id
        """
        try:
            response = self._make_request('POST', 'orders/create/adhoc', data=order_data)
            return response
            
        except Exception as e:
            current_app.logger.error(f"ShipRocket order creation failed: {str(e)}")
            raise
    
    def assign_awb(self, shipment_id, courier_id):
        """
        Assign AWB (Airway Bill) to shipment
        
        Args:
            shipment_id (int): ShipRocket shipment ID
            courier_id (int): Courier ID from serviceability response
        
        Returns:
            dict: AWB assignment response with awb_code and courier_name
        """
        try:
            data = {
                'shipment_id': shipment_id,
                'courier_id': courier_id
            }
            
            response = self._make_request('POST', 'courier/assign/awb', data=data)
            return response
            
        except Exception as e:
            current_app.logger.error(f"AWB assignment failed: {str(e)}")
            raise
    
    def generate_pickup(self, shipment_id):
        """
        Generate pickup request for shipment
        
        Args:
            shipment_id (int): ShipRocket shipment ID
        
        Returns:
            dict: Pickup generation response
        """
        try:
            data = {
                'shipment_id': shipment_id
            }
            
            response = self._make_request('POST', 'courier/generate/pickup', data=data)
            return response
            
        except Exception as e:
            current_app.logger.error(f"Pickup generation failed: {str(e)}")
            raise
    
    def create_shiprocket_order_from_db_order(self, order_id, merchant_id, pickup_address_id, delivery_address_id, courier_id=None):
        """
        Create ShipRocket order from database order
        
        Args:
            order_id (str): Internal order ID
            merchant_id (int): Merchant ID
            pickup_address_id (int): Pickup address ID
            delivery_address_id (int): Delivery address ID
            courier_id (int, optional): Preferred courier ID
        
        Returns:
            dict: Complete shipping process response
        """
        try:
            # Get order details
            order = Order.query.filter_by(order_id=order_id).first()
            if not order:
                raise Exception(f"Order {order_id} not found")
            
            # Get merchant details
            merchant = MerchantProfile.query.filter_by(id=merchant_id).first()
            if not merchant:
                raise Exception(f"Merchant {merchant_id} not found")
            
            # Get addresses
            pickup_address = None
            if pickup_address_id:
                pickup_address = UserAddress.query.filter_by(address_id=pickup_address_id).first()
            # Fallback: use merchant business address as pickup
            if not pickup_address:
                class _Addr: pass
                pickup_address = _Addr()
                pickup_address.postal_code = merchant.postal_code
                pickup_address.address_line1 = merchant.business_address
                pickup_address.address_line2 = ""
                pickup_address.city = merchant.city
                pickup_address.state_province = merchant.state_province
                pickup_address.country_code = merchant.country_code
                pickup_address.contact_name = merchant.business_name
                pickup_address.contact_phone = merchant.business_phone
            
            delivery_address = UserAddress.query.filter_by(address_id=delivery_address_id).first()
            
            if not pickup_address:
                raise Exception(f"Pickup address {pickup_address_id} not found")
            if not delivery_address:
                raise Exception(f"Delivery address {delivery_address_id} not found")
            
            # Calculate total weight and prepare order items
            total_weight = Decimal('0')
            total_length = Decimal('0')
            total_breadth = Decimal('0')
            total_height = Decimal('0')
            order_items = []
            
            for item in order.items:
                if item.merchant_id == merchant_id:
                    # Get product shipping details
                    product = Product.query.filter_by(product_id=item.product_id).first()
                    if product and hasattr(product, 'shipping') and product.shipping:
                        # Use actual shipping dimensions from product_shipping
                        item_weight = product.shipping.weight_kg or Decimal('0.5')  # Default 0.5kg if not set
                        item_length = product.shipping.length_cm or Decimal('10')  # Default 10cm if not set
                        item_breadth = product.shipping.width_cm or Decimal('10')  # Default 10cm if not set
                        item_height = product.shipping.height_cm or Decimal('10')  # Default 10cm if not set
                    else:
                        # Default dimensions if no shipping info available
                        item_weight = Decimal('0.5')  # Default weight
                        item_length = Decimal('10')  # Default length
                        item_breadth = Decimal('10')  # Default breadth
                        item_height = Decimal('10')  # Default height
                    
                    # Calculate totals for the entire shipment
                    total_weight += item_weight * item.quantity
                    # For dimensions, we'll use the largest item's dimensions as the package dimensions
                    # This is a common approach for multiple items in one package
                    if item_length > total_length:
                        total_length = item_length
                    if item_breadth > total_breadth:
                        total_breadth = item_breadth
                    if item_height > total_height:
                        total_height = item_height
                    
                    current_app.logger.info(f"Product {item.product_id} shipping details: weight={item_weight}kg, length={item_length}cm, breadth={item_breadth}cm, height={item_height}cm")
                    
                    order_items.append({
                        "name": item.product_name_at_purchase,
                        "sku": item.sku_at_purchase,
                        "units": str(item.quantity),
                        "selling_price": str(int(float(item.unit_price_inclusive_gst))),
                        "discount": str(int(float(item.discount_amount_per_unit_applied))) if item.discount_amount_per_unit_applied else "",
                        "tax": str(int(float(item.gst_amount_per_unit))) if item.gst_amount_per_unit else "",
                        "hsn": ""  # HSN code - can be added later if available
                    })
            
            # Check serviceability
            # Calculate COD amount with proper limits
            cod_amount = 0
            if order.payment_status.value != 'paid':
                cod_amount = float(order.total_amount)
                # Cap COD amount at ShipRocket's limit (typically 50k)
                if cod_amount > 50000:
                    current_app.logger.warning(f"COD amount {cod_amount} exceeds limit, capping at 50000")
                    cod_amount = 50000
            
            serviceability_response = self.check_serviceability(
                pickup_pincode=pickup_address.postal_code,
                delivery_pincode=delivery_address.postal_code,
                weight=float(total_weight),
                cod=0 if order.payment_status.value == 'paid' else float(order.total_amount)
            )
            
            if not serviceability_response.get('data', {}).get('available_courier_companies'):
                raise Exception("No courier services available for this route")
            
            # Select the best courier service.
            available_couriers = serviceability_response['data']['available_courier_companies']

            # If the caller specified a courier_id and it is in the list, honour that choice.
            selected_courier = None
            if courier_id:
                selected_courier = next((c for c in available_couriers if c['courier_company_id'] == courier_id), None)

            # Otherwise pick the courier with the best rating and, for equal ratings, the lowest price.
            if not selected_courier:
                # ShipRocket returns rating as string/int ("4.3") and rate as float/int.
                def _sort_key(c):
                    try:
                        rating = float(c.get('rating', 0))
                    except (TypeError, ValueError):
                        rating = 0.0
                    try:
                        price = float(c.get('rate', 0))
                    except (TypeError, ValueError):
                        price = float('inf')
                    # Highest rating first (negative for descending), then lowest price
                    return (-rating, price)

                available_couriers_sorted = sorted(available_couriers, key=_sort_key)
                selected_courier = available_couriers_sorted[0]
                
                current_app.logger.info(f"Auto-selected best courier: {selected_courier.get('courier_name', 'Unknown')} "
                                      f"(Rating: {selected_courier.get('rating', 'N/A')}, "
                                      f"Rate: ₹{selected_courier.get('rate', 'N/A')})")
            
            # Clean up courier data to return only essential information
            cleaned_courier = self._clean_courier_data(selected_courier)
            
            # For now, let's create a shipment record in our database even if ShipRocket order creation fails
            # This will help with tracking and we can retry ShipRocket order creation later
            
            current_app.logger.info(f"Creating shipment record for order {order_id}, merchant {merchant_id}")
            
            # Create or update shipment record in database
            existing_shipment = Shipment.query.filter_by(
                order_id=order_id, 
                merchant_id=merchant_id
            ).first()
            
            if existing_shipment:
                current_app.logger.info(f"Updating existing shipment {existing_shipment.shipment_id}")
                # Update existing shipment
                existing_shipment.carrier_name = selected_courier.get('courier_name', 'Unknown')
                existing_shipment.shipment_status = ShipmentStatusEnum.PENDING_PICKUP
                existing_shipment.courier_id = selected_courier.get('courier_company_id')
                existing_shipment.pickup_address_id = pickup_address_id
                existing_shipment.delivery_address_id = delivery_address_id
                shipment = existing_shipment
            else:
                current_app.logger.info(f"Creating new shipment record for order {order_id}, merchant {merchant_id}")
                # Create new shipment record
                shipment = Shipment(
                    order_id=order_id,
                    merchant_id=merchant_id,
                    carrier_name=selected_courier.get('courier_name', 'Unknown'),
                    shipment_status=ShipmentStatusEnum.PENDING_PICKUP,
                    courier_id=selected_courier.get('courier_company_id'),
                    pickup_address_id=pickup_address_id,
                    delivery_address_id=delivery_address_id
                )
                db.session.add(shipment)
            
            try:
                db.session.commit()
                current_app.logger.info(f"Successfully saved shipment record: {shipment.shipment_id}")
            except Exception as db_error:
                current_app.logger.error(f"Database error saving shipment: {str(db_error)}")
                db.session.rollback()
                raise
            
            # Try to create ShipRocket order (but don't fail if it doesn't work)
            shiprocket_order_id = None
            shipment_id = None
            awb_code = None
            courier_name = selected_courier.get('courier_name', 'Unknown')
            
            try:
                # Split customer name into first and last name
                customer_name = delivery_address.contact_name or f"{order.user.first_name} {order.user.last_name}"
                name_parts = customer_name.strip().split(' ', 1)
                billing_first_name = name_parts[0] if name_parts else ""
                billing_last_name = name_parts[1] if len(name_parts) > 1 else ""
                
                # Get or create merchant's pickup location
                pickup_location_name = self.get_or_create_merchant_pickup_location(merchant_id)
                current_app.logger.info(f"Using pickup location '{pickup_location_name}' for merchant {merchant_id}")
                
                # Prepare order data for ShipRocket according to official API requirements
                order_data = {
                    "order_id": order_id,
                    "order_date": order.order_date.strftime("%Y-%m-%d %H:%M"),  # Include time
                    "pickup_location": pickup_location_name,
                    "comment": "",
                    "reseller_name": merchant.business_name,
                    "company_name": merchant.business_name,
                    "billing_customer_name": billing_first_name,
                    "billing_last_name": billing_last_name,
                    "billing_address": delivery_address.address_line1,
                    "billing_address_2": delivery_address.address_line2 or "",
                    "billing_isd_code": "",
                    "billing_city": delivery_address.city,
                    "billing_pincode": delivery_address.postal_code,
                    "billing_state": delivery_address.state_province,
                    "billing_country": delivery_address.country_code,
                    "billing_email": order.user.email,
                    "billing_phone": self._format_phone_number(delivery_address.contact_phone or order.user.phone),
                    "billing_alternate_phone": "",
                    "shipping_is_billing": "1",
                    "shipping_customer_name": "",  # Empty when shipping_is_billing is True
                    "shipping_last_name": "",  # Empty when shipping_is_billing is True
                    "shipping_address": "",  # Empty when shipping_is_billing is True
                    "shipping_address_2": "",  # Empty when shipping_is_billing is True
                    "shipping_city": "",  # Empty when shipping_is_billing is True
                    "shipping_pincode": "",  # Empty when shipping_is_billing is True
                    "shipping_country": "",  # Empty when shipping_is_billing is True
                    "shipping_state": "",  # Empty when shipping_is_billing is True
                    "shipping_email": "",  # Empty when shipping_is_billing is True
                    "shipping_phone": "",  # Empty when shipping_is_billing is True
                    "order_items": order_items,
                    "payment_method": "Prepaid" if order.payment_status.value == 'paid' else "COD",
                    "shipping_charges": str(int(float(order.shipping_amount or 0))),
                    "giftwrap_charges": "",
                    "transaction_charges": "",
                    "total_discount": "",
                    "sub_total": str(int(float(order.total_amount))),
                    "length": str(float(total_length)),
                    "breadth": str(float(total_breadth)),
                    "height": str(float(total_height)),
                    "weight": str(float(total_weight)),
                    "ewaybill_no": "",
                    "customer_gstin": "",
                    "invoice_number": "",
                    "order_type": ""
                }
                
                current_app.logger.info(f"Final shipping dimensions for order {order_id}: length={total_length}cm, breadth={total_breadth}cm, height={total_height}cm, weight={total_weight}kg")
                
                # Ensure minimum dimensions and weight if no shipping info was found
                if total_weight <= 0:
                    total_weight = Decimal('0.5')  # Minimum 0.5kg
                    current_app.logger.warning(f"No shipping weight found for order {order_id}, using default 0.5kg")
                if total_length <= 0:
                    total_length = Decimal('10')  # Minimum 10cm
                    current_app.logger.warning(f"No shipping length found for order {order_id}, using default 10cm")
                if total_breadth <= 0:
                    total_breadth = Decimal('10')  # Minimum 10cm
                    current_app.logger.warning(f"No shipping breadth found for order {order_id}, using default 10cm")
                if total_height <= 0:
                    total_height = Decimal('10')  # Minimum 10cm
                    current_app.logger.warning(f"No shipping height found for order {order_id}, using default 10cm")
                
                # Validate required fields before sending to ShipRocket
                required_fields = ['order_id', 'billing_customer_name', 'billing_address', 'billing_city', 'billing_pincode', 'billing_state', 'billing_country', 'billing_email', 'billing_phone']
                for field in required_fields:
                    if not order_data.get(field):
                        current_app.logger.warning(f"Missing required field for ShipRocket order: {field}")
                
                if not order_items:
                    current_app.logger.warning("No order items found for ShipRocket order")

                # Create order in ShipRocket
                order_response = self.create_order(order_data)
                
                if order_response.get('status') == 200:
                    shiprocket_order_id = order_response['data']['order_id']
                    shipment_id = order_response['data']['shipment_id']
                    
                    # Assign AWB
                    awb_response = self.assign_awb(shipment_id, selected_courier['courier_company_id'])
                    
                    if awb_response.get('status') == 200:
                        awb_code = awb_response['data']['awb_code']
                        courier_name = awb_response['data']['courier_name']
                        
                        # Generate pickup
                        pickup_response = self.generate_pickup(shipment_id)
                        
                        if pickup_response.get('status') == 200:
                            # Update shipment with ShipRocket details
                            shipment.shiprocket_order_id = shiprocket_order_id
                            shipment.shiprocket_shipment_id = shipment_id
                            shipment.awb_code = awb_code
                            shipment.tracking_number = awb_code
                            shipment.carrier_name = courier_name
                            shipment.shipment_status = ShipmentStatusEnum.LABEL_CREATED
                            shipment.shipped_date = datetime.now(timezone.utc)
                            shipment.pickup_generated = True
                            shipment.pickup_generated_at = datetime.now(timezone.utc)
                            db.session.commit()
                            
                            current_app.logger.info(f"ShipRocket order created successfully for merchant {merchant_id}")
                        else:
                            current_app.logger.warning(f"Pickup generation failed: {pickup_response.get('message', 'Unknown error')}")
                    else:
                        current_app.logger.warning(f"AWB assignment failed: {awb_response.get('message', 'Unknown error')}")
                else:
                    current_app.logger.warning(f"ShipRocket order creation failed: {order_response.get('message', 'Unknown error')}")
                    
            except Exception as shiprocket_error:
                current_app.logger.warning(f"ShipRocket order creation failed for merchant {merchant_id}: {str(shiprocket_error)}")
                # Don't fail the entire process if ShipRocket fails
            
            return {
                "success": True,
                "shiprocket_order_id": shiprocket_order_id,
                "shipment_id": shipment_id,
                "awb_code": awb_code,
                "courier_name": courier_name,
                "tracking_number": awb_code,
                "serviceability": serviceability_response,
                "db_shipment": shipment.serialize(),
                "courier_data": cleaned_courier
            }
            
        except Exception as e:
            current_app.logger.error(f"ShipRocket order creation failed: {str(e)}")
            db.session.rollback()
            raise
    
    def get_tracking_details(self, awb_code):
        """
        Get tracking details for a shipment
        
        Args:
            awb_code (str): AWB code
        
        Returns:
            dict: Tracking details
        """
        try:
            params = {'awb': awb_code}
            response = self._make_request('GET', 'courier/track/shipment/', params=params)
            return response
            
        except Exception as e:
            current_app.logger.error(f"Tracking details fetch failed: {str(e)}")
            raise
    
    def get_tracking_by_order_id(self, order_id, channel_id=None):
        """
        Get tracking details for a shipment using order ID and channel ID
        
        Args:
            order_id (str): Order ID from your store
            channel_id (int, optional): Channel ID corresponding to the store
        
        Returns:
            dict: Tracking details
        """
        try:
            params = {'order_id': order_id}
            if channel_id:
                params['channel_id'] = channel_id
            
            current_app.logger.info(f"Getting tracking details for order_id: {order_id}, channel_id: {channel_id}")
            current_app.logger.info(f"ShipRocket API URL: {self.BASE_URL}/courier/track")
            current_app.logger.info(f"Request params: {params}")
            
            response = self._make_request('GET', 'courier/track', params=params)
            
            current_app.logger.info(f"ShipRocket tracking response for order {order_id}: {response}")
            
            return response
            
        except Exception as e:
            current_app.logger.error(f"Tracking details fetch failed for order_id {order_id}: {str(e)}")
            raise
    
    def get_shipment_tracking(self, shipment_id):
        """
        Get tracking details for a shipment using shipment ID from database
        
        Args:
            shipment_id (int): Shipment ID from database
        
        Returns:
            dict: Tracking details
        """
        try:
            # Get shipment details from database
            shipment = Shipment.query.filter_by(shipment_id=shipment_id).first()
            if not shipment:
                raise Exception(f"Shipment {shipment_id} not found")
            
            # Check if we have ShipRocket order ID
            if not shipment.shiprocket_order_id:
                raise Exception(f"No ShipRocket order ID found for shipment {shipment_id}")
            
            current_app.logger.info(f"Getting tracking for shipment {shipment_id}, ShipRocket order_id: {shipment.shiprocket_order_id}")
            
            # Use the order ID from ShipRocket for tracking
            return self.get_tracking_by_order_id(
                order_id=str(shipment.shiprocket_order_id),
                channel_id=shipment.merchant_id if shipment.merchant_id else None
            )
            
        except Exception as e:
            current_app.logger.error(f"Shipment tracking failed for shipment_id {shipment_id}: {str(e)}")
            raise
    
    def get_tracking_by_db_order_id(self, db_order_id):
        """
        Get tracking details using order_id from your database Order model
        
        Args:
            db_order_id (str): Order ID from your database (e.g., "ORD-20250728114812-8D8759")
        
        Returns:
            dict: Tracking details for all shipments of this order
        """
        try:
            # Get order from database to verify it exists
            order = Order.query.filter_by(order_id=db_order_id).first()
            if not order:
                raise Exception(f"Order {db_order_id} not found")
            
            current_app.logger.info(f"Getting tracking directly from ShipRocket for order: {db_order_id}")
            
            # Call ShipRocket tracking API directly with the order ID
            # This will return tracking data even if the order hasn't been shipped through ShipRocket yet
            tracking_response = self.get_tracking_by_order_id(
                order_id=db_order_id,
                channel_id=None  # We'll let ShipRocket determine the channel
            )
            
            current_app.logger.info(f"ShipRocket tracking response for order {db_order_id}: {tracking_response}")
            
            # Return the direct ShipRocket response
            return {
                "order_id": db_order_id,
                "shiprocket_response": tracking_response
            }
            
        except Exception as e:
            current_app.logger.error(f"Tracking failed for order_id {db_order_id}: {str(e)}")
            raise
    
    def create_shiprocket_orders_for_all_merchants(self, order_id, delivery_address_id, courier_id=None):
        """
        Create ShipRocket orders for all merchants involved in a single order
        
        Args:
            order_id (str): Internal order ID
            delivery_address_id (int): Delivery address ID
            courier_id (int, optional): Preferred courier ID for all shipments
        
        Returns:
            dict: Complete shipping process response for all merchants
        """
        try:
            current_app.logger.info(f"Starting bulk ShipRocket order creation for order {order_id}")
            
            # Get order details
            order = Order.query.filter_by(order_id=order_id).first()
            if not order:
                raise Exception(f"Order {order_id} not found")
            
            # Get delivery address
            delivery_address = UserAddress.query.filter_by(address_id=delivery_address_id).first()
            if not delivery_address:
                raise Exception(f"Delivery address {delivery_address_id} not found")
            
            current_app.logger.info(f"Found order with {len(order.items)} items")
            
            # Group order items by merchant
            merchant_items = {}
            for item in order.items:
                if item.merchant_id not in merchant_items:
                    merchant_items[item.merchant_id] = []
                merchant_items[item.merchant_id].append(item)
            
            current_app.logger.info(f"Order has items from {len(merchant_items)} merchants: {list(merchant_items.keys())}")
            
            if not merchant_items:
                raise Exception("No merchant items found in order")
            
            # Create ShipRocket orders for each merchant
            merchant_responses = {}
            successful_merchants = []
            failed_merchants = []
            
            for merchant_id, items in merchant_items.items():
                try:
                    current_app.logger.info(f"Creating ShipRocket order for merchant {merchant_id} in order {order_id} with {len(items)} items")
                    
                    # Create ShipRocket order for this merchant
                    response = self.create_shiprocket_order_from_db_order(
                        order_id=order_id,
                        merchant_id=merchant_id,
                        pickup_address_id=None,  # Will use merchant's address
                        delivery_address_id=delivery_address_id,
                        courier_id=courier_id
                    )
                    
                    merchant_responses[merchant_id] = response
                    successful_merchants.append(merchant_id)
                    
                    current_app.logger.info(f"Successfully created ShipRocket order for merchant {merchant_id}")
                    
                except Exception as e:
                    current_app.logger.error(f"Failed to create ShipRocket order for merchant {merchant_id}: {str(e)}")
                    merchant_responses[merchant_id] = {
                        "success": False,
                        "error": str(e)
                    }
                    failed_merchants.append(merchant_id)
            
            current_app.logger.info(f"Bulk ShipRocket order creation completed. Successful: {len(successful_merchants)}, Failed: {len(failed_merchants)}")
            
            return {
                "success": len(successful_merchants) > 0,
                "total_merchants": len(merchant_items),
                "successful_merchants": successful_merchants,
                "failed_merchants": failed_merchants,
                "merchant_responses": merchant_responses,
                "order_id": order_id
            }
            
        except Exception as e:
            current_app.logger.error(f"Bulk ShipRocket order creation failed: {str(e)}")
            raise
    
    def add_pickup_location(self, pickup_data):
        """
        Add pickup location to ShipRocket
        
        Args:
            pickup_data (dict): Pickup location data with fields:
                - pickup_location: Location name (e.g., "Primary", "Warehouse 1")
                - name: Contact person name
                - email: Contact email
                - phone: Contact phone
                - address: Full address
                - city: City
                - state: State
                - country: Country code
                - pin_code: Postal code
                - address_type: "Primary" or "Secondary"
        
        Returns:
            dict: ShipRocket response with pickup location details
        """
        try:
            response = self._make_request('POST', 'settings/company/addpickup', data=pickup_data)
            return response
            
        except Exception as e:
            current_app.logger.error(f"Failed to add pickup location: {str(e)}")
            raise
    
    def get_pickup_locations(self):
        """
        Get all pickup locations from ShipRocket
        
        Returns:
            dict: List of pickup locations
        """
        try:
            response = self._make_request('GET', 'settings/company/pickup')
            
            # Log the response structure for debugging
            current_app.logger.info(f"ShipRocket pickup locations response structure: {list(response.keys()) if isinstance(response, dict) else 'Not a dict'}")
            if isinstance(response, dict) and 'data' in response:
                current_app.logger.info(f"Data structure: {list(response['data'].keys()) if isinstance(response['data'], dict) else 'Data not a dict'}")
            
            return response
            
        except Exception as e:
            current_app.logger.error(f"Failed to get pickup locations: {str(e)}")
            raise
    
    def create_merchant_pickup_location(self, merchant_id):
        """
        Create pickup location in ShipRocket for a merchant
        
        Args:
            merchant_id (int): Merchant ID
        
        Returns:
            str: Pickup location name (even if creation fails)
        """
        try:
            # Get merchant details
            merchant = MerchantProfile.query.filter_by(id=merchant_id).first()
            if not merchant:
                raise Exception(f"Merchant {merchant_id} not found")
            
            # Prepare pickup location data
            pickup_location_name = f"Merchant_{merchant_id}_{merchant.business_name.replace(' ', '_')}"
            
            pickup_data = {
                "pickup_location": pickup_location_name,
                "name": merchant.contact_person_name or merchant.business_name,
                "email": merchant.business_email,
                "phone": self._format_phone_number(merchant.business_phone),
                "address": merchant.business_address,
                "address_2": "",  # Add missing field
                "city": merchant.city,
                "state": merchant.state_province,
                "country": merchant.country_code,
                "pin_code": merchant.postal_code
            }
            
            # Validate required fields for pickup location
            required_pickup_fields = ['pickup_location', 'name', 'email', 'phone', 'address', 'city', 'state', 'country', 'pin_code']
            for field in required_pickup_fields:
                if not pickup_data.get(field):
                    current_app.logger.warning(f"Missing required field for pickup location: {field}")
            
            current_app.logger.info(f"Creating pickup location for merchant {merchant_id}: {pickup_location_name}")
            
            try:
                # Add pickup location to ShipRocket
                response = self.add_pickup_location(pickup_data)
                
                if response.get('status') == 200:
                    # Update merchant profile with ShipRocket pickup location ID
                    pickup_location_id = response.get('data', {}).get('pickup_location_id')
                    if pickup_location_id:
                        merchant.shiprocket_pickup_location_id = pickup_location_id
                        merchant.shiprocket_pickup_location_name = pickup_location_name
                        db.session.commit()
                        current_app.logger.info(f"Updated merchant {merchant_id} with ShipRocket pickup location ID: {pickup_location_id}")
                    
                    return pickup_location_name
                else:
                    current_app.logger.warning(f"Failed to create pickup location: {response.get('message', 'Unknown error')}")
                    # Return the pickup location name anyway
                    return pickup_location_name
                    
            except Exception as e:
                error_msg = str(e)
                # Check if it's the "already exists and is inactive" error
                if "already exists and is inactive" in error_msg:
                    current_app.logger.info(f"Pickup location '{pickup_location_name}' already exists but is inactive. Using it anyway.")
                    # Update merchant profile with the pickup location name
                    merchant.shiprocket_pickup_location_name = pickup_location_name
                    db.session.commit()
                    return pickup_location_name
                else:
                    current_app.logger.warning(f"Failed to create pickup location for merchant {merchant_id}: {error_msg}")
                    # Return the pickup location name anyway
                    return pickup_location_name
                
        except Exception as e:
            current_app.logger.error(f"Failed to create pickup location for merchant {merchant_id}: {str(e)}")
            # Return a fallback pickup location name
            return f"Merchant_{merchant_id}"
    
    def get_or_create_merchant_pickup_location(self, merchant_id):
        """
        Get existing pickup location for merchant or create new one
        
        Args:
            merchant_id (int): Merchant ID
        
        Returns:
            str: Pickup location name
        """
        try:
            # Get merchant details
            merchant = MerchantProfile.query.filter_by(id=merchant_id).first()
            if not merchant:
                raise Exception(f"Merchant {merchant_id} not found")
            
            # Check if merchant already has a ShipRocket pickup location
            if merchant.shiprocket_pickup_location_name:
                current_app.logger.info(f"Using existing pickup location for merchant {merchant_id}: {merchant.shiprocket_pickup_location_name}")
                return merchant.shiprocket_pickup_location_name
            
            # Create new pickup location
            current_app.logger.info(f"No pickup location found for merchant {merchant_id}, creating new one")
            pickup_location_name = self.create_merchant_pickup_location(merchant_id)
            
            # The create_merchant_pickup_location method now returns the pickup location name
            # even if creation fails, so we can use it
            current_app.logger.info(f"Using pickup location for merchant {merchant_id}: {pickup_location_name}")
            return pickup_location_name
                
        except Exception as e:
            current_app.logger.error(f"Error getting pickup location for merchant {merchant_id}: {str(e)}")
            # Fallback to merchant-specific pickup location name
            return f"Merchant_{merchant_id}" 

    def create_shiprocket_order_for_shop(self, shop_order_id, shop_id, delivery_address_id, courier_id=None):
        """
        Create ShipRocket order for a shop order where the shop is the primary pickup location
        
        Args:
            shop_order_id (str): Shop order ID from database
            shop_id (int): Shop ID
            delivery_address_id (int): Delivery address ID
            courier_id (int, optional): Preferred courier ID
        
        Returns:
            dict: Complete shipping process response
        """
        try:
            # Get shop order details
            from models.shop.shop_order import ShopOrder
            from models.shop.shop import Shop
            from models.user_address import UserAddress
            
            shop_order = ShopOrder.query.filter_by(order_id=shop_order_id).first()
            if not shop_order:
                raise Exception(f"Shop order {shop_order_id} not found")
            
            # Get shop details
            shop = Shop.query.filter_by(shop_id=shop_id).first()
            if not shop:
                raise Exception(f"Shop {shop_id} not found")
            
            # Get delivery address
            delivery_address = UserAddress.query.filter_by(address_id=delivery_address_id).first()
            if not delivery_address:
                raise Exception(f"Delivery address {delivery_address_id} not found")
            
            # Create shop pickup location if it doesn't exist
            pickup_location_name = self.get_or_create_shop_pickup_location(shop_id)
            current_app.logger.info(f"Using pickup location '{pickup_location_name}' for shop {shop_id}")
            
            # Calculate total weight and prepare order items
            total_weight = Decimal('0')
            total_length = Decimal('0')
            total_breadth = Decimal('0')
            total_height = Decimal('0')
            order_items = []
            
            for item in shop_order.items:
                # Get product shipping details
                from models.shop.shop_product import ShopProduct
                product = ShopProduct.query.filter_by(product_id=item.product_id).first()
                
                if product and hasattr(product, 'shipping') and product.shipping:
                    # Use actual shipping dimensions from product_shipping
                    item_weight = product.shipping.weight_kg or Decimal('0.5')
                    item_length = product.shipping.length_cm or Decimal('10')
                    item_breadth = product.shipping.width_cm or Decimal('10')
                    item_height = product.shipping.height_cm or Decimal('10')
                else:
                    # Default dimensions if no shipping info available
                    item_weight = Decimal('0.5')
                    item_length = Decimal('10')
                    item_breadth = Decimal('10')
                    item_height = Decimal('10')
                
                # Calculate totals for the entire shipment
                total_weight += item_weight * item.quantity
                # For dimensions, use the largest item's dimensions
                if item_length > total_length:
                    total_length = item_length
                if item_breadth > total_breadth:
                    total_breadth = item_breadth
                if item_height > total_height:
                    total_height = item_height
                
                current_app.logger.info(f"Product {item.product_id} shipping details: weight={item_weight}kg, length={item_length}cm, breadth={item_breadth}cm, height={item_height}cm")
                
                order_items.append({
                    "name": item.product_name_at_purchase,
                    "sku": item.sku_at_purchase,
                    "units": str(item.quantity),
                    "selling_price": str(int(float(item.unit_price_inclusive_gst))),
                    "discount": str(int(float(item.discount_amount_per_unit_applied or 0))),
                    "tax": str(int(float(item.gst_amount_per_unit or 0))),
                    "hsn": ""
                })
            
            # Check serviceability
            cod_amount = 0
            if shop_order.payment_status.value != 'paid':
                cod_amount = float(shop_order.total_amount)
                # Cap COD amount at ShipRocket's limit
                if cod_amount > 50000:
                    current_app.logger.warning(f"COD amount {cod_amount} exceeds limit, capping at 50000")
                    cod_amount = 50000
            
            # Get primary pickup location pincode from ShipRocket
            pickup_pincode = "110001"  # Default fallback
            try:
                pickup_locations_response = self.get_pickup_locations()
                if pickup_locations_response.get('status') == 200:
                    pickup_locations = pickup_locations_response.get('data', {}).get('data', [])
                    for location in pickup_locations:
                        if location.get('address_type') == 'Primary' or location.get('is_primary') == True:
                            pickup_pincode = location.get('pin_code', '110001')
                            current_app.logger.info(f"Using primary pickup location pincode: {pickup_pincode}")
                            break
            except Exception as e:
                current_app.logger.warning(f"Failed to get primary pickup location pincode: {str(e)}, using default")
            
            serviceability_response = self.check_serviceability(
                pickup_pincode=pickup_pincode,
                delivery_pincode=delivery_address.postal_code,
                weight=float(total_weight),
                cod=0 if shop_order.payment_status.value == 'paid' else float(shop_order.total_amount)
            )
            
            if not serviceability_response.get('data', {}).get('available_courier_companies'):
                raise Exception("No courier services available for this route")
            
            # Select the best courier service
            available_couriers = serviceability_response['data']['available_courier_companies']
            
            # If the caller specified a courier_id and it is in the list, honour that choice
            selected_courier = None
            if courier_id:
                selected_courier = next((c for c in available_couriers if c['courier_company_id'] == courier_id), None)
            
            # Otherwise pick the courier with the best rating and lowest price
            if not selected_courier:
                def _sort_key(c):
                    try:
                        rating = float(c.get('rating', 0))
                    except (TypeError, ValueError):
                        rating = 0.0
                    try:
                        price = float(c.get('rate', 0))
                    except (TypeError, ValueError):
                        price = float('inf')
                    return (-rating, price)
                
                available_couriers_sorted = sorted(available_couriers, key=_sort_key)
                selected_courier = available_couriers_sorted[0]
                
                current_app.logger.info(f"Auto-selected best courier: {selected_courier.get('courier_name', 'Unknown')} "
                                      f"(Rating: {selected_courier.get('rating', 'N/A')}, "
                                      f"Rate: ₹{selected_courier.get('rate', 'N/A')})")
            
            # Clean up courier data
            cleaned_courier = self._clean_courier_data(selected_courier)
            
            # Create or update shipment record in database
            from models.shop.shop_shipment import ShopShipment
            from models.shipment import ShipmentStatusEnum
            
            existing_shipment = ShopShipment.query.filter_by(
                shop_order_id=shop_order_id, 
                shop_id=shop_id
            ).first()
            
            if existing_shipment:
                current_app.logger.info(f"Updating existing shipment {existing_shipment.shipment_id}")
                existing_shipment.carrier_name = selected_courier.get('courier_name', 'Unknown')
                existing_shipment.shipment_status = ShipmentStatusEnum.PENDING_PICKUP
                existing_shipment.courier_id = selected_courier.get('courier_company_id')
                existing_shipment.pickup_address_id = None  # Shop pickup location
                existing_shipment.delivery_address_id = delivery_address_id
                shipment = existing_shipment
            else:
                current_app.logger.info(f"Creating new shipment record for shop order {shop_order_id}, shop {shop_id}")
                from models.shop.shop_shipment import ShopShipment
                shipment = ShopShipment(
                    shop_order_id=shop_order_id,
                    shop_id=shop_id,
                    carrier_name=selected_courier.get('courier_name', 'Unknown'),
                    shipment_status=ShipmentStatusEnum.PENDING_PICKUP,
                    courier_id=selected_courier.get('courier_company_id'),
                    pickup_address_id=None,  # Shop pickup location
                    delivery_address_id=delivery_address_id
                )
                db.session.add(shipment)
            
            try:
                db.session.commit()
                current_app.logger.info(f"Successfully saved shipment record: {shipment.shipment_id}")
            except Exception as db_error:
                current_app.logger.error(f"Database error saving shipment: {str(db_error)}")
                db.session.rollback()
                raise
            
            # Try to create ShipRocket order
            shiprocket_order_id = None
            shipment_id = None
            awb_code = None
            courier_name = selected_courier.get('courier_name', 'Unknown')
            
            try:
                # Split customer name into first and last name
                customer_name = delivery_address.contact_name or f"{shop_order.user.first_name} {shop_order.user.last_name}"
                name_parts = customer_name.strip().split(' ', 1)
                billing_first_name = name_parts[0] if name_parts else ""
                billing_last_name = name_parts[1] if len(name_parts) > 1 else ""
                
                # Prepare order data for ShipRocket
                order_data = {
                    "order_id": shop_order_id,
                    "order_date": shop_order.order_date.strftime("%Y-%m-%d %H:%M"),
                    "pickup_location": pickup_location_name,
                    "comment": "",
                    "reseller_name": shop.name,
                    "company_name": shop.name,
                    "billing_customer_name": billing_first_name,
                    "billing_last_name": billing_last_name,
                    "billing_address": delivery_address.address_line1,
                    "billing_address_2": delivery_address.address_line2 or "",
                    "billing_isd_code": "",
                    "billing_city": delivery_address.city,
                    "billing_pincode": delivery_address.postal_code,
                    "billing_state": delivery_address.state_province,
                    "billing_country": delivery_address.country_code,
                    "billing_email": shop_order.user.email,
                    "billing_phone": self._format_phone_number(delivery_address.contact_phone or shop_order.user.phone),
                    "billing_alternate_phone": "",
                    "shipping_is_billing": "1",
                    "shipping_customer_name": "",
                    "shipping_last_name": "",
                    "shipping_address": "",
                    "shipping_address_2": "",
                    "shipping_city": "",
                    "shipping_pincode": "",
                    "shipping_country": "",
                    "shipping_state": "",
                    "shipping_email": "",
                    "shipping_phone": "",
                    "order_items": order_items,
                    "payment_method": "Prepaid" if shop_order.payment_status.value == 'paid' else "COD",
                    "shipping_charges": str(int(float(shop_order.shipping_amount or 0))),
                    "giftwrap_charges": "",
                    "transaction_charges": "",
                    "total_discount": "",
                    "sub_total": str(int(float(shop_order.total_amount))),
                    "length": str(float(total_length)),
                    "breadth": str(float(total_breadth)),
                    "height": str(float(total_height)),
                    "weight": str(float(total_weight)),
                    "ewaybill_no": "",
                    "customer_gstin": "",
                    "invoice_number": "",
                    "order_type": ""
                }
                
                current_app.logger.info(f"Final shipping dimensions for shop order {shop_order_id}: length={total_length}cm, breadth={total_breadth}cm, height={total_height}cm, weight={total_weight}kg")
                
                # Ensure minimum dimensions and weight
                if total_weight <= 0:
                    total_weight = Decimal('0.5')
                    current_app.logger.warning(f"No shipping weight found for shop order {shop_order_id}, using default 0.5kg")
                if total_length <= 0:
                    total_length = Decimal('10')
                    current_app.logger.warning(f"No shipping length found for shop order {shop_order_id}, using default 10cm")
                if total_breadth <= 0:
                    total_breadth = Decimal('10')
                    current_app.logger.warning(f"No shipping breadth found for shop order {shop_order_id}, using default 10cm")
                if total_height <= 0:
                    total_height = Decimal('10')
                    current_app.logger.warning(f"No shipping height found for shop order {shop_order_id}, using default 10cm")
                
                # Validate required fields
                required_fields = ['order_id', 'billing_customer_name', 'billing_address', 'billing_city', 'billing_pincode', 'billing_state', 'billing_country', 'billing_email', 'billing_phone']
                for field in required_fields:
                    if not order_data.get(field):
                        current_app.logger.warning(f"Missing required field for ShipRocket shop order: {field}")
                
                if not order_items:
                    current_app.logger.warning("No order items found for ShipRocket shop order")
                
                # Create order in ShipRocket
                order_response = self.create_order(order_data)
                
                if order_response.get('status') == 200:
                    shiprocket_order_id = order_response['data']['order_id']
                    shipment_id = order_response['data']['shipment_id']
                    
                    # Assign AWB
                    awb_response = self.assign_awb(shipment_id, selected_courier['courier_company_id'])
                    
                    if awb_response.get('status') == 200:
                        awb_code = awb_response['data']['awb_code']
                        courier_name = awb_response['data']['courier_name']
                        
                        # Generate pickup
                        pickup_response = self.generate_pickup(shipment_id)
                        
                        if pickup_response.get('status') == 200:
                            # Update shipment with ShipRocket details
                            shipment.shiprocket_order_id = shiprocket_order_id
                            shipment.shiprocket_shipment_id = shipment_id
                            shipment.awb_code = awb_code
                            shipment.tracking_number = awb_code
                            shipment.carrier_name = courier_name
                            shipment.shipment_status = ShipmentStatusEnum.LABEL_CREATED
                            shipment.shipped_date = datetime.now(timezone.utc)
                            shipment.pickup_generated = True
                            shipment.pickup_generated_at = datetime.now(timezone.utc)
                            db.session.commit()
                            
                            current_app.logger.info(f"ShipRocket shop order created successfully for shop {shop_id}")
                        else:
                            current_app.logger.warning(f"Pickup generation failed: {pickup_response.get('message', 'Unknown error')}")
                    else:
                        current_app.logger.warning(f"AWB assignment failed: {awb_response.get('message', 'Unknown error')}")
                else:
                    current_app.logger.warning(f"ShipRocket shop order creation failed: {order_response.get('message', 'Unknown error')}")
                    
            except Exception as shiprocket_error:
                current_app.logger.warning(f"ShipRocket shop order creation failed for shop {shop_id}: {str(shiprocket_error)}")
                # Don't fail the entire process if ShipRocket fails
            
            return {
                "success": True,
                "shiprocket_order_id": shiprocket_order_id,
                "shipment_id": shipment_id,
                "awb_code": awb_code,
                "courier_name": courier_name,
                "tracking_number": awb_code,
                "serviceability": serviceability_response,
                "db_shipment": shipment.serialize(),
                "courier_data": cleaned_courier
            }
            
        except Exception as e:
            current_app.logger.error(f"ShipRocket shop order creation failed: {str(e)}")
            db.session.rollback()
            raise
    
    def create_shop_pickup_location(self, shop_id):
        """
        Get the primary pickup location from ShipRocket instead of creating new ones
        
        Args:
            shop_id (int): Shop ID
        
        Returns:
            str: Primary pickup location name from ShipRocket
        """
        try:
            # Get shop details for logging
            from models.shop.shop import Shop
            shop = Shop.query.filter_by(shop_id=shop_id).first()
            if not shop:
                raise Exception(f"Shop {shop_id} not found")
            
            current_app.logger.info(f"Getting primary pickup location from ShipRocket for shop {shop_id}")
            
            try:
                # Get all pickup locations from ShipRocket
                pickup_locations_response = self.get_pickup_locations()
                
                if pickup_locations_response.get('status') == 200:
                    # Try different possible response structures
                    pickup_locations = []
                    
                    # Structure 1: data.data (nested)
                    if 'data' in pickup_locations_response and isinstance(pickup_locations_response['data'], dict):
                        if 'data' in pickup_locations_response['data']:
                            pickup_locations = pickup_locations_response['data']['data']
                        elif 'pickup_locations' in pickup_locations_response['data']:
                            pickup_locations = pickup_locations_response['data']['pickup_locations']
                        elif isinstance(pickup_locations_response['data'], list):
                            pickup_locations = pickup_locations_response['data']
                    
                    # Structure 2: direct data array
                    elif isinstance(pickup_locations_response.get('data'), list):
                        pickup_locations = pickup_locations_response['data']
                    
                    current_app.logger.info(f"Found {len(pickup_locations)} pickup locations")
                    
                    # Find the primary pickup location or Aoin location
                    primary_pickup = None
                    for location in pickup_locations:
                        pickup_name = location.get('pickup_location', 'Unknown')
                        address_type = location.get('address_type', 'Unknown')
                        is_primary = location.get('is_primary', False)
                        
                        current_app.logger.info(f"Checking pickup location: {pickup_name} - type: {address_type} - primary: {is_primary}")
                        
                        # First priority: Look for "Aoin" location
                        if pickup_name.lower() == 'aoin':
                            primary_pickup = location
                            current_app.logger.info(f"Found Aoin pickup location: {pickup_name}")
                            break
                        # Second priority: Look for primary location
                        elif (address_type == 'Primary' or 
                              is_primary == True or 
                              pickup_name.lower() == 'primary'):
                            primary_pickup = location
                            current_app.logger.info(f"Found primary pickup location: {pickup_name}")
                            break
                    
                    if primary_pickup:
                        pickup_location_name = primary_pickup.get('pickup_location', 'Primary')
                        current_app.logger.info(f"Found primary pickup location: {pickup_location_name}")
                        
                        # Update shop with the primary pickup location info
                        shop.shiprocket_pickup_location_name = pickup_location_name
                        shop.shiprocket_pickup_location_id = primary_pickup.get('pickup_location_id')
                        db.session.commit()
                        
                        return pickup_location_name
                    elif pickup_locations:
                        # Use the first available pickup location as fallback
                        first_location = pickup_locations[0]
                        pickup_location_name = first_location.get('pickup_location', 'Primary')
                        current_app.logger.info(f"No primary pickup location found, using first available: {pickup_location_name}")
                        
                        # Update shop with the pickup location info
                        shop.shiprocket_pickup_location_name = pickup_location_name
                        shop.shiprocket_pickup_location_id = first_location.get('pickup_location_id')
                        db.session.commit()
                        
                        return pickup_location_name
                    else:
                        current_app.logger.warning("No pickup locations found in ShipRocket, using 'Aoin' as fallback")
                        return "Aoin"
                else:
                    current_app.logger.warning(f"Failed to get pickup locations from ShipRocket: {pickup_locations_response.get('message', 'Unknown error')}")
                    return "Aoin"
                    
            except Exception as e:
                current_app.logger.warning(f"Failed to get pickup locations from ShipRocket for shop {shop_id}: {str(e)}")
                return "Aoin"
                
        except Exception as e:
            current_app.logger.error(f"Failed to get pickup location for shop {shop_id}: {str(e)}")
            return "Aoin"
    
    def get_or_create_shop_pickup_location(self, shop_id):
        """
        Get the primary pickup location from ShipRocket for all shops
        
        Args:
            shop_id (int): Shop ID
        
        Returns:
            str: Primary pickup location name from ShipRocket
        """
        try:
            # Get shop details for logging
            from models.shop.shop import Shop
            shop = Shop.query.filter_by(shop_id=shop_id).first()
            if not shop:
                raise Exception(f"Shop {shop_id} not found")
            
            # Always get the primary pickup location from ShipRocket
            current_app.logger.info(f"Getting primary pickup location from ShipRocket for shop {shop_id}")
            pickup_location_name = self.create_shop_pickup_location(shop_id)
            
            current_app.logger.info(f"Using primary pickup location for shop {shop_id}: {pickup_location_name}")
            return pickup_location_name
                
        except Exception as e:
            current_app.logger.error(f"Error getting pickup location for shop {shop_id}: {str(e)}")
            return "Aoin" 