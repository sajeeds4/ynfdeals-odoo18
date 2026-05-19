#!/usr/bin/env python3
import json
from pathlib import Path

DATA_FILE = Path(__file__).with_name('data.json')


def load():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}


def save(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))
    print(f'Updated {DATA_FILE}')


def prompt(default, label):
    current = default if default is not None else ''
    value = input(f'{label} [{current}]: ').strip()
    return value or current


def main():
    data = load()
    print('Update the OBS overlay data. Press Enter to keep current values.\n')

    data['sellerName'] = prompt(data.get('sellerName'), 'Seller name')
    data['productTitle'] = prompt(data.get('productTitle'), 'Product title')
    notes = data.setdefault('notes', {})
    notes['top'] = prompt(notes.get('top'), 'Top note')
    notes['mid'] = prompt(notes.get('mid'), 'Mid note')
    notes['base'] = prompt(notes.get('base'), 'Base note')
    data['retailPrice'] = prompt(data.get('retailPrice'), 'Retail price')
    data['shippingText'] = prompt(data.get('shippingText'), 'Shipping text')
    data['promoText'] = prompt(data.get('promoText'), 'Promo text')
    data['bidText'] = prompt(data.get('bidText'), 'Bid text')
    data['bidCount'] = prompt(data.get('bidCount'), 'Bid count')
    data['ctaText'] = prompt(data.get('ctaText'), 'Bottom CTA text')
    data['ctaCount'] = prompt(data.get('ctaCount'), 'Bottom CTA count')
    data['likeCount'] = prompt(data.get('likeCount'), 'Like count')
    data['statsLine'] = prompt(data.get('statsLine'), 'Stats line')

    print('\nEnter up to 4 chat lines:')
    chat = []
    for i in range(1, 5):
        default_user = (data.get('chatLines') or [{}]*4)[i-1].get('user', '') if data.get('chatLines') else ''
        default_msg = (data.get('chatLines') or [{}]*4)[i-1].get('message', '') if data.get('chatLines') else ''
        user = prompt(default_user, f'Chat {i} user')
        msg = prompt(default_msg, f'Chat {i} message')
        if user or msg:
            chat.append({'user': user, 'message': msg})
    data['chatLines'] = chat

    print('\nEnter ticker items separated by |')
    default_ticker = ' | '.join(data.get('tickerItems', []))
    ticker = prompt(default_ticker, 'Ticker items')
    data['tickerItems'] = [item.strip() for item in ticker.split('|') if item.strip()]

    save(data)


if __name__ == '__main__':
    main()
