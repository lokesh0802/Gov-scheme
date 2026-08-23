// import http from 'k6/http';
// import { check } from 'k6';

// export const options = {
//     stages: [
//         { duration: '2m', target: 1000 },
//         { duration: '2m', target: 2500 },
//         { duration: '2m', target: 5000 },
//         { duration: '2m', target: 7500 },
//         { duration: '2m', target: 10000 },
//         { duration: '2m', target: 0 },
//     ],
// };
// export default function () {
//     const payload = JSON.stringify({
//         event: "message.received",
//         timestamp: "2026-07-10T12:26:02.028Z",
//         sessionId: "83b8a03f-628b-43e4-8912-808e900671f9",
//         idempotencyKey: "msg_unknown",
//         deliveryId: "dlv_8a67b229-6eeb-490c-ae5e-a1621dff8631",
//         data: {
//             id: "false_121264207343725@lid_3B957D8CAD6E057C506F",
//             from: "121264207343725@lid",
//             to: "918901975539@c.us",
//             chatId: "121264207343725@lid",
//             body: "hi",
//             type: "chat",
//             timestamp: 1783686361,
//             fromMe: false,
//             isGroup: false
//         }
//     });

//     const params = {
//         headers: {
//             "Content-Type": "application/json",
//         },
//     };

//     const res = http.post("http://localhost:8000/webhook", payload, params);

//     check(res, {
//         "status is 200": (r) => r.status === 200,
//     });
// }
import http from 'k6/http';
import { check } from 'k6';

export const options = {
    stages: [
        { duration: '1m', target: 1 },
        // { duration: '1m', target: 500 },
        // { duration: '1m', target: 1000 },
        // { duration: '1m', target: 2000 },
        // { duration: '1m', target: 5000 },
        // { duration: '1m', target: 10000 },
        // { duration: '1m', target: 0 },
    ],
};

export default function () {
    // Har Virtual User ke liye unique user
    const userId = `${100000000000 + __VU}@lid`;

    const payload = JSON.stringify({
        event: "message.received",
        timestamp: new Date().toISOString(),
        sessionId: "83b8a03f-628b-43e4-8912-808e900671f9",
        idempotencyKey: `msg-${__VU}-${__ITER}`,
        deliveryId: `delivery-${__VU}-${__ITER}`,
        data: {
            id: `message-${__VU}-${__ITER}`,
            from: userId,
            to: "918683815254@c.us",
            chatId: userId,
            body: "Hi",
            type: "chat",
            timestamp: Math.floor(Date.now() / 1000),
            fromMe: false,
            isGroup: false
        }
    });

    const params = {
        headers: {
            "Content-Type": "application/json",
        },
        timeout: "120s", // Wait up to 2 minutes for a response
    };

    const res = http.post(
        "http://localhost:8000/webhook",
        payload,
        params
    );

    check(res, {
        "status is 200": (r) => r.status === 200,
    });
}