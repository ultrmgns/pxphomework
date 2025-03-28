import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
# Optional: for more realistic fake data
# from faker import Faker
# fake = Faker()

# --- Configuration ---
NUM_MERCHANTS = 1000
NUM_TRANSACTIONS_TARGET = 500000 # Target total transactions
SIMULATION_DAYS = 30 # Simulate activity over 30 days
START_DATE = datetime.now() - timedelta(days=SIMULATION_DAYS)

# Define some MCCs and their typical transaction profiles (example)
MCC_PROFILES = {
    '5812': {'name': 'Restaurants', 'avg_ticket': 40, 'std_dev': 20, 'daily_txn_base': 50},
    '5411': {'name': 'Grocery Stores', 'avg_ticket': 60, 'std_dev': 30, 'daily_txn_base': 100},
    '5541': {'name': 'Gas Stations', 'avg_ticket': 50, 'std_dev': 15, 'daily_txn_base': 80},
    '7999': {'name': 'Misc Rec Services', 'avg_ticket': 75, 'std_dev': 50, 'daily_txn_base': 20},
    '5999': {'name': 'Misc Retail', 'avg_ticket': 100, 'std_dev': 75, 'daily_txn_base': 30},
    '4814': {'name': 'Telecom Services', 'avg_ticket': 80, 'std_dev': 20, 'daily_txn_base': 10}, # Often lower volume, higher ticket
    '5732': {'name': 'Electronics Stores', 'avg_ticket': 250, 'std_dev': 150, 'daily_txn_base': 15}, # Higher ticket
}
VALID_MCCS = list(MCC_PROFILES.keys())

HIGH_RISK_COUNTRIES = ['CY', 'LV', 'MT', 'PA', 'RU'] # Example list
COMMON_COUNTRIES = ['US', 'GB', 'DE', 'FR', 'CA', 'AU']

CARD_TYPES = ['Credit', 'Debit', 'Prepaid']
# Adjust weights: e.g., more Credit/Debit normally
NORMAL_CARD_TYPE_WEIGHTS = [0.5, 0.45, 0.05]
SUSPICIOUS_PREPAID_WEIGHTS = [0.3, 0.3, 0.4] # Higher prepaid %

# --- Generate Merchants ---
merchants_list = []
for i in range(NUM_MERCHANTS):
    mcc = random.choice(VALID_MCCS)
    country = random.choices(COMMON_COUNTRIES + HIGH_RISK_COUNTRIES, weights=[10]*len(COMMON_COUNTRIES) + [1]*len(HIGH_RISK_COUNTRIES), k=1)[0] # Skew towards common, some high risk
    merchants_list.append({
        'merchant_id': f'M{1000 + i}',
        'mcc': mcc,
        'merchant_name': MCC_PROFILES[mcc]['name'] + f" {i}", # Simple name
        'country': country,
        'ownership_changed_recently': random.choice([True, False, False, False]), # 1 in 4 chance
        'baseline_risk': 'High' if country in HIGH_RISK_COUNTRIES else random.choices(['Low', 'Medium'], weights=[0.8, 0.2], k=1)[0]
    })
merchants_df = pd.DataFrame(merchants_list)

# --- Decide which merchants will be suspicious ---
suspicious_merchant_ids = merchants_df.sample(frac=0.1).merchant_id.tolist() # Make 10% suspicious

# --- Generate Transactions ---
transactions_list = []
transaction_id_counter = 0

for _, merchant in merchants_df.iterrows():
    merchant_id = merchant['merchant_id']
    mcc = merchant['mcc']
    profile = MCC_PROFILES[mcc]
    is_suspicious = merchant_id in suspicious_merchant_ids

    # Calculate number of transactions for this merchant
    # Adjust daily base by some randomness, sum over days
    merchant_total_txns = int(max(1, np.random.normal(profile['daily_txn_base'], profile['daily_txn_base']*0.3)) * SIMULATION_DAYS)

    # --- Inject Suspicious Flags (can combine multiple) ---
    inject_high_prepaid = is_suspicious and random.random() < 0.5 # 50% chance if suspicious
    inject_rounded_values = is_suspicious and random.random() < 0.4 # 40% chance
    inject_mcc_mismatch = is_suspicious and random.random() < 0.3 # 30% chance
    inject_structuring = is_suspicious and random.random() < 0.2 # 20% chance
    inject_velocity_spike = is_suspicious and random.random() < 0.15 # 15% chance

    # Determine card type weights for this merchant
    current_card_type_weights = SUSPICIOUS_PREPAID_WEIGHTS if inject_high_prepaid else NORMAL_CARD_TYPE_WEIGHTS

    # Simulate velocity spike period if needed
    spike_start_day, spike_end_day = -1, -1
    if inject_velocity_spike:
        spike_start_day = random.randint(5, SIMULATION_DAYS - 6)
        spike_end_day = spike_start_day + random.randint(1, 3) # Spike lasts 1-3 days

    # Generate transactions day by day (or just distribute randomly over time)
    for _ in range(merchant_total_txns):
        transaction_id_counter += 1
        txn_day = random.randint(0, SIMULATION_DAYS - 1)
        timestamp = START_DATE + timedelta(days=txn_day, hours=random.uniform(0, 24))

        # Base amount
        amount = max(1.0, np.random.normal(profile['avg_ticket'], profile['std_dev']))

        # --- Apply Suspicious Modifications ---
        is_rounded = False
        if inject_rounded_values and random.random() < 0.3: # 30% of txns are rounded if profile active
            amount = round(amount / 10) * 10 # Round to nearest 10
            if amount == 0: amount = 10.0
            is_rounded = True

        if inject_mcc_mismatch:
             # If low ticket MCC, sometimes generate high value
            if profile['avg_ticket'] < 100 and random.random() < 0.1:
                amount = max(amount, np.random.uniform(500, 2000))
            # If high ticket MCC, sometimes generate very low value
            elif profile['avg_ticket'] > 150 and random.random() < 0.1:
                 amount = max(1.0, np.random.uniform(1, 10))

        # Note: Structuring is harder to simulate perfectly without state.
        # Simple approach: Occasionally generate a burst of small txns near a large one.
        # This is better done by analyzing the *output* data, but we can bias generation slightly.
        if inject_structuring and random.random() < 0.05: # Bias towards smaller amounts sometimes
             amount = max(1.0, amount * random.uniform(0.05, 0.2))

        # Apply velocity spike multiplier
        if inject_velocity_spike and spike_start_day <= txn_day <= spike_end_day:
             # This doesn't directly increase count easily here, but we could inflate values
             # A better way would be to increase `merchant_total_txns` based on spike days
             pass # Placeholder - better to adjust total count generation

        # --- Other Attributes ---
        card_type = random.choices(CARD_TYPES, weights=current_card_type_weights, k=1)[0]
        # Simulate card IDs - need some repetition
        # Simple: pool of cards, some used more often, some shared across merchants (esp. suspicious ones)
        # Advanced: Use faker for fake credit card numbers (but still need to manage reuse)
        card_id_token = f'Card_{random.randint(1, int(NUM_TRANSACTIONS_TARGET / 10))}' # Simple reuse simulation

        card_country = random.choices(
            COMMON_COUNTRIES + HIGH_RISK_COUNTRIES,
            weights=[20]*len(COMMON_COUNTRIES) + ([5] if merchant['country'] in HIGH_RISK_COUNTRIES else [1])*len(HIGH_RISK_COUNTRIES), # Bias towards merchant country, higher risk if merchant is high risk
            k=1)[0]

        transactions_list.append({
            'transaction_id': f'T{1000000 + transaction_id_counter}',
            'merchant_id': merchant_id,
            'timestamp': timestamp,
            'amount': round(amount, 2),
            'currency': 'USD', # Assuming USD for simplicity
            'card_id_token': card_id_token,
            'card_type': card_type,
            'card_country': card_country,
            'is_rounded': is_rounded,
            'is_error': 0 # Assuming all successful for now
        })

transactions_df = pd.DataFrame(transactions_list)

# --- Adjust total transaction count if needed ---
if len(transactions_df) > NUM_TRANSACTIONS_TARGET:
    transactions_df = transactions_df.sample(n=NUM_TRANSACTIONS_TARGET).reset_index(drop=True)
elif len(transactions_df) < NUM_TRANSACTIONS_TARGET:
    print(f"Warning: Generated {len(transactions_df)} transactions, less than target {NUM_TRANSACTIONS_TARGET}.")


# --- Save to CSV ---
merchants_df.to_csv('synthetic_merchants.csv', index=False)
transactions_df.to_csv('synthetic_transactions.csv', index=False)

print(f"Generated {len(merchants_df)} merchants in synthetic_merchants.csv")
print(f"Generated {len(transactions_df)} transactions in synthetic_transactions.csv")
print("\nSample Merchants:")
print(merchants_df.head())
print("\nSample Transactions:")
print(transactions_df.head())
print(f"\nPercentage of suspicious merchants: {len(suspicious_merchant_ids)/NUM_MERCHANTS:.1%}")
print(f"Percentage of prepaid transactions: {len(transactions_df[transactions_df['card_type']=='Prepaid'])/len(transactions_df):.1%}")
print(f"Percentage of rounded transactions: {transactions_df['is_rounded'].mean():.1%}")