# Loyalty points skill

When a customer reports missing loyalty points:
1. Always verify order ownership matches the customer before applying points
2. Check payment method — gift cards are ineligible for points accrual
3. Check discount_code — some promo codes disable points accrual
4. If points_applied is false and no disqualifying factors exist, apply manually
5. Flag if the order date clusters with other failures — may indicate a systemic bug