from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from controllers import merchant_transaction_controller as txn_ctrl

merchant_transaction_bp = Blueprint('merchant_transaction', __name__)

@merchant_transaction_bp.route('/merchant-transactions/from-order', methods=['POST', 'OPTIONS'])
def create_transaction_from_order():
    """
    Create merchant transaction(s) from an order
    ---
    tags:
      - Merchant Transactions
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - order_id
            properties:
              order_id:
                type: string
                description: Order ID to create merchant transactions for
    responses:
      201:
        description: Merchant transactions created successfully
        schema:
          type: object
          properties:
            status:
              type: string
            transactions:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  order_id:
                    type: string
                  merchant_id:
                    type: integer
                  order_amount:
                    type: number
                  final_payable_amount:
                    type: number
                  payment_status:
                    type: string
                  settlement_date:
                    type: string
      400:
        description: Bad request - Missing order_id
      401:
        description: Unauthorized - JWT required
      500:
        description: Internal server error
    """
    # Handle OPTIONS request for CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    # Apply JWT requirement only for POST requests
    @jwt_required()
    def _create_transaction():
        data = request.get_json()
        order_id = data.get('order_id')
        if not order_id:
            return jsonify({'status': 'error', 'message': 'order_id is required'}), 400
        try:
            transactions = txn_ctrl.create_merchant_transaction_from_order(order_id)
            return jsonify({'status': 'success', 'transactions': [t.serialize() for t in transactions]}), 201
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    
    return _create_transaction()

@merchant_transaction_bp.route('/merchant-transactions/<int:txn_id>', methods=['GET', 'OPTIONS'])
def get_transaction(txn_id):
    """
    Get details of a specific merchant transaction
    ---
    tags:
      - Merchant Transactions
    parameters:
      - in: path
        name: txn_id
        type: integer
        required: true
        description: ID of the merchant transaction to retrieve
    responses:
      200:
        description: Merchant transaction details retrieved successfully
        schema:
          type: object
          properties:
            status:
              type: string
            transaction:
              type: object
              properties:
                id:
                  type: integer
                order_id:
                  type: string
                merchant_id:
                  type: integer
                order_amount:
                  type: number
                final_payable_amount:
                  type: number
                payment_status:
                  type: string
                settlement_date:
                  type: string
      401:
        description: Unauthorized - JWT required
      404:
        description: Merchant transaction not found
      500:
        description: Internal server error
    """
    # Handle OPTIONS request for CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    # Apply JWT requirement only for GET requests
    @jwt_required()
    def _get_transaction():
        txn = txn_ctrl.get_transaction_by_id(txn_id)
        return jsonify({'status': 'success', 'transaction': txn.serialize()})
    
    return _get_transaction()

@merchant_transaction_bp.route('/merchant-transactions', methods=['GET', 'OPTIONS'])
def list_transactions():
    """
    Get a list of all merchant transactions with optional filters
    ---
    tags:
      - Merchant Transactions
    parameters:
      - in: query
        name: status
        type: string
        required: false
        description: Filter by payment status (e.g., pending, paid)
      - in: query
        name: merchant_id
        type: integer
        required: false
        description: Filter by merchant ID
      - in: query
        name: from_date
        type: string
        format: date
        required: false
        description: Filter transactions from this date (YYYY-MM-DD)
      - in: query
        name: to_date
        type: string
        format: date
        required: false
        description: Filter transactions up to this date (YYYY-MM-DD)
    responses:
      200:
        description: List of merchant transactions retrieved successfully
        schema:
          type: object
          properties:
            status:
              type: string
            transactions:
              type: array
              items:
                type: object
                properties:
                  id:
                    type: integer
                  order_id:
                    type: string
                  merchant_id:
                    type: integer
                  order_amount:
                    type: number
                  final_payable_amount:
                    type: number
                  payment_status:
                    type: string
                  settlement_date:
                    type: string
      401:
        description: Unauthorized - JWT required
      500:
        description: Internal server error
    """
    # Handle OPTIONS request for CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    # Apply JWT requirement only for GET requests
    @jwt_required()
    def _list_transactions():
        filters = {
            'status': request.args.get('status'),
            'merchant_id': request.args.get('merchant_id'),
            'from_date': request.args.get('from_date'),
            'to_date': request.args.get('to_date'),
        }
        txns = txn_ctrl.list_all_transactions(filters)
        return jsonify({'status': 'success', 'transactions': [t.serialize() for t in txns]})
    
    return _list_transactions()
