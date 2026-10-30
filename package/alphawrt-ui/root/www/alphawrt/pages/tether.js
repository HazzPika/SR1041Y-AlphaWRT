/*
 * Mobile: a phone (iPhone, Android) or USB modem in the USB port shares its
 * Internet as a second WAN, usbwan. Off, a backup (it carries the traffic
 * while the main Internet is down) or always. The phone comes from
 * alphawrt tether; the mode is the network config: usbwan's metric against
 * the WAN's, so the kernel's default route does the failover.
 */
import { h, icon, badge, card, rows, fmtTime, toast, redraw } from '../lib/ui.js';
import { maybe, uci } from '../lib/rpc.js';
import { save } from '../lib/apply.js';

const KIND = { iphone: 'iPhone', android: 'Android phone', usb: 'USB modem' };
const MODES = [
	[ 'backup', 'Backup', 'Only while the main Internet is down, for example when the fibre is cut. It switches back by itself.', 'Recommended' ],
	[ 'always', 'Always', 'The phone is the Internet, even while the main connection is up.' ],
	[ 'off', 'Off', 'Never use the phone.' ]
];

const bytes = n => n >= 1e9 ? `${(n / 1e9).toFixed(2)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round((n || 0) / 1e3)} kB`;

/* backup: usbwan below the WAN (metric 20); always: above it (the WAN moves to 30) */
const modeOps = mode => [
	[ 'set', 'network', 'usbwan', { disabled: mode == 'off' ? '1' : '0', metric: mode == 'always' ? '0' : '20' } ],
	mode == 'always' ? [ 'set', 'network', 'wan', { metric: '30' } ] : [ 'unset', 'network', 'wan', 'metric' ],
	[ 'set', 'alphawrt', 'tether', { mode }, 'tether' ]
];

function modeCard(value, title, text, tag, cur, onpick) {
	const r = h('input', { type: 'radio', name: 'tether-mode', class: 'radio radio-primary radio-sm mt-1', checked: cur == value });
	r.addEventListener('change', () => onpick(value));
	return h('label', { class: 'flex gap-3 p-4 rounded-box bg-base-100 border border-base-300 cursor-pointer has-[:checked]:border-primary has-[:checked]:ring-1 has-[:checked]:ring-primary' },
		r, h('span', { class: 'flex-1 min-w-0' },
			h('span', { class: 'flex items-center gap-2 font-semibold' }, title, tag && h('span', { class: 'badge badge-soft badge-primary badge-sm' }, tag)),
			h('span', { class: 'block text-sm opacity-70 mt-1' }, text)));
}

const steps = (title, list) => h('div', {}, h('h3', { class: 'font-semibold text-sm' }, title),
	h('ol', { class: 'text-sm opacity-80 mt-1 space-y-1' }, list.map((s, i) => h('li', {}, `${i + 1}. ${s}`))));

export default {
	title: 'Mobile',

	async render(main) {
		await uci.load('network', 'alphawrt');
		main.append(h('h1', { class: 'text-2xl font-bold' }, 'Mobile'));
		if (!uci.get('network', 'usbwan'))
			return main.append(card('phone', 'Phone Internet', badge('off', 'Unavailable'),
				h('p', { class: 'text-sm opacity-70' }, 'This image has no USB tethering set up.')));

		const saved = uci.get('alphawrt', 'tether', 'mode') || (uci.get('network', 'usbwan', 'disabled') == '1' ? 'off' : 'backup');
		let pick = saved;
		const btn = h('button', { type: 'button', class: 'btn btn-primary', disabled: true, onclick: async () => {
			btn.disabled = true;
			const ok = await save(modeOps(pick), { what: 'Saving' }).catch(e => { toast('bad', e.message); return null; });
			if (ok) { toast('ok', 'Saved'); redraw(); }
			else btn.disabled = false;
		} }, 'Save');
		const picker = h('div', { class: 'space-y-3' }, MODES.map(([ v, t, x, tag ]) => modeCard(v, t, x, tag, saved, p => { pick = p; btn.disabled = p == saved; })));
		const status = h('div');

		main.append(status,
			card('wand', 'Use the phone', null, h('div', {}, picker,
				h('p', { class: 'text-xs opacity-70 mt-3' }, 'Backup switches over when the main connection drops (the login or the cable). If that connection stays up but your provider’s network fails, it doesn’t.'),
				h('div', { class: 'card-actions justify-end mt-4' }, btn))),
			card('cable', 'How to connect', null, h('div', { class: 'space-y-4' },
				/* in this order: a first-time pairing with the hotspot already on has reset an SR1041Y */
				steps('iPhone', [ 'Plug it into the USB port with a data cable.', 'Settings → Personal Hotspot → Allow Others to Join: on.', 'Tap Trust on the iPhone and enter its passcode (first time only).' ]),
				steps('Android', [ 'Plug it into the USB port with a data cable.', 'Settings → Network → Hotspot & tethering → USB tethering: on.' ]),
				h('p', { class: 'text-xs opacity-70' }, 'Your mobile plan may count this as hotspot data.'))));

		const tick = async () => {
			const [ t, dump ] = await Promise.all([ maybe('alphawrt', 'tether'), maybe('network.interface', 'dump') ]);
			const ifs = dump.interface || [], u = ifs.find(i => i.interface == 'usbwan'), wan = ifs.find(i => i.interface == 'wan');
			const dev = t.device ? await maybe('network.device', 'status', { name: t.device }) : {}, s = dev.statistics || {};
			const used = u?.up && (saved == 'always' || !wan?.up);
			const st = !t.supported ? badge('off', 'Not supported')
				: !t.device ? badge('off', 'No phone')
				: saved == 'off' ? badge('off', 'Off')
				: !u?.up ? badge('warn', 'No Internet from the phone')
				: used ? badge('ok', 'In use') : badge('ok', 'Standing by');
			status.replaceChildren(card('phone', 'Phone', st, !t.device
				? h('p', { class: 'text-sm opacity-70' }, t.supported ? 'No phone in the USB port. See How to connect below.' : 'This image has no USB tethering driver.')
				: rows([
					[ 'Phone', [ KIND[t.kind] || 'USB device', t.product && t.product != KIND[t.kind] ? ` (${t.product})` : '' ].join('') ],
					[ 'Status', saved == 'off' ? 'Off' : !u?.up ? 'Waiting for the phone' : used ? 'Carrying the Internet' : 'Ready, the main Internet is up' ],
					u?.up && [ 'Address from the phone', u['ipv4-address']?.[0]?.address || '—' ],
					u?.up && [ 'Connected for', fmtTime(u.uptime || 0) ],
					[ 'Data through the phone', `${bytes(s.rx_bytes)} down · ${bytes(s.tx_bytes)} up` ]
				])));
		};
		await tick();
		return tick;
	}
};
