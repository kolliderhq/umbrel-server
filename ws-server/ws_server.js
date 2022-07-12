const ws = require("ws");
const zmq = require("zeromq");

const AUTHENTICATION = "authentication";
const SEND_PAYMENT = "sendPayment";
const CREATE_INVOICE = "createInvoice";
const GET_CHANNEL_BALANCES = "getChannelBalances";
const GET_WALLET_BALANCES = "getWalletBalances";
const GET_NODE_INFO = "getNodeInfo";
const GET_HEDGE_STATE = "getHedgeState";
const GET_WALLET_STATE = "getWalletState";
const SET_TARGET_HEDGE = "setTargetHedge";
const LNURL_AUTH = "lnurlAuth";
const LNURL_AUTH_HEDGE = "lnurlAuthHedge";
const CREATE_NEW_HEDGE = "createNewHedge";

let ZMQ_ADDRESS = "";
let ZMQ_SUB_ADDRESS = "";
let ZMQ_HEDGER_ADDRESS = "";

if (process.env.DEV) {
  ZMQ_PUB_ADDRESS = "tcp://*:5556";
  ZMQ_SUB_ADDRESS = "tcp://127.0.0.1:5557";
} else {
  ZMQ_PUB_ADDRESS = process.env.KOLLIDER_ZMQ_PUB_ADDRESS;
  ZMQ_SUB_ADDRESS = process.env.KOLLIDER_ZMQ_SUB_ADDRESS;
}

const createResponse = (data, type) => {
  const resp = {
    type: type,
    data: data,
  };
  return JSON.stringify(resp);
};

async function zmqInvoiceSubscriber(onMessage) {
  const subSocket = new zmq.Subscriber();

  await subSocket.connect(ZMQ_SUB_ADDRESS);
  subSocket.subscribe("lnd_server_pub_stream");

  for await (const [topic, msg] of subSocket) {
    onMessage(msg);
  }
}

const wss = new ws.WebSocketServer({
  port: 8080,
  perMessageDeflate: false,
});

const pubSocket = new zmq.Publisher();

pubSocket.bind(ZMQ_PUB_ADDRESS).then(_ => {
  const sendToBack = (msg) => {
    pubSocket.send(["lnd_server_sub_stream", msg])
  }
  wss.on("connection", function connection(ws) {
    let isSubscribed = false;
    const onZmqReply = (msg) => {
      let jstring = msg.toString();
      jstring = JSON.parse(jstring);
      jstring.map((m) => {
        ws.send(JSON.stringify(m));
      });
    };

    ws.on("message", function message(data) {
      let d = "";
      try {
        d = JSON.parse(data);
        console.log(d)
      } catch (err) {
        return null;
      }
      if (!isSubscribed) {
        isSubscribed = true;
        zmqInvoiceSubscriber(onZmqReply);
      }
      if (d.type === CREATE_INVOICE) {
        let amount = d.amount;
        if (!amount) {
          ws.send(createResponse({ msg: "Amount not specified" }, "error"));
        } else {
          const msg = {
            action: "create_invoice",
            data: {
              amount: d.amount,
            },
          };
          sendToBack(JSON.stringify(msg));
        }
      } else if (d.type === SEND_PAYMENT) {
        if (!d.paymentRequest) {
          const data = {
            msg: "Payment request not provided.",
          };
          ws.send(createResponse(data, "error"));
        } else {
          const msg = {
            action: "send_payment",
            data: {
              status: "success",
              payment_request: d.paymentRequest,
            },
          };
          sendToBack(JSON.stringify(msg));
        }
      } else if (d.type === GET_NODE_INFO) {
        const msg = {
          action: "get_node_info",
        };
        sendToBack(JSON.stringify(msg));
      } else if (d.type === GET_CHANNEL_BALANCES) {
        const msg = {
          action: "get_channel_balances",
        };
        sendToBack(JSON.stringify(msg));
      } else if (d.type === GET_WALLET_BALANCES) {
        const msg = {
          action: "get_wallet_balances",
        };
        sendToBack(JSON.stringify(msg));
      } else if (d.type === LNURL_AUTH) {
        const msg = {
          action: "lnurl_auth",
          data: { lnurl: d.lnurl },
        };
        sendToBack(JSON.stringify(msg));
      } else {
        ws.send(createResponse({ msg: "action not available" }, "error"));
      }
    });
  });
})
