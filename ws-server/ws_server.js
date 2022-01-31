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
  ZMQ_ADDRESS = "tcp://127.0.0.1:5556";
  ZMQ_SUB_ADDRESS = "tcp://127.0.0.1:5557";
  ZMQ_HEDGER_ADDRESS = "tcp://127.0.0.1:5558";
  ZMQ_HEDGER_SUB_ADDRESS = "tcp://127.0.0.1:5559";
} else {
  ZMQ_ADDRESS = process.env.KOLLIDER_ZMQ_ADDRESS;
  ZMQ_SUB_ADDRESS = process.env.KOLLIDER_ZMQ_SUB_ADDRESS;
  ZMQ_HEDGER_ADDRESS = process.env.KOLLIDER_ZMQ_HEDGER_ADDRESS;
  ZMQ_HEDGER_SUB_ADDRESS = process.env.KOLLIDER_ZMQ_HEDGER_SUB_ADDRESS;
}

const createResponse = (data, type) => {
  const resp = {
    type: type,
    data: data,
  };
  return JSON.stringify(resp);
};

async function zmqSubscriber(onMessage) {
  const subSocket = new zmq.Subscriber();

  await subSocket.connect(ZMQ_SUB_ADDRESS);
  subSocket.subscribe("invoices");

  for await (const [topic, msg] of subSocket) {
    onMessage(msg);
  }
}

async function zmqHedgerSubscriber(onMessage) {
  const subSocket = new zmq.Subscriber();

  await subSocket.connect(ZMQ_HEDGER_SUB_ADDRESS);
  subSocket.subscribe("hedger_stream");

  for await (const [topic, msg] of subSocket) {
    onMessage(msg);
  }
}

async function zmqLndRequest(msg, onReply) {
  const socket = new zmq.Request();
  socket.connect(ZMQ_ADDRESS);
  await socket.send(msg);
  const [result] = await socket.receive();
  onReply(result);
}

async function zmqHedgerRequest(msg, onReply) {
  const socket = new zmq.Request();
  socket.connect(ZMQ_HEDGER_ADDRESS);
  await socket.send(msg);
  const [result] = await socket.receive();
  onReply(result);
}

const wss = new ws.WebSocketServer({
  port: 8080,
  perMessageDeflate: false,
});

wss.on("connection", function connection(ws) {
  let isAuthenticated = true;

  const onZmqReply = (msg) => {
    ws.send(msg.toString());
  };

  zmqSubscriber(onZmqReply);
  zmqHedgerSubscriber(onZmqReply)

  ws.on("message", function message(data) {
    let d = "";
    try {
      d = JSON.parse(data);
    } catch (err) {
      return null;
    }
    if (d.type === AUTHENTICATION) {
      let env_password = process.env.APP_PASSWORD;
      if (d.password === env_password) {
        const data = {
          status: "success",
        };
        isAuthenticated = true;
        ws.send(createResponse(data, "authentication"));
      } else {
        const data = {
          msg: "wrong password",
        };
        ws.send(createResponse(data, "authentication"));
      }
    }

    if (!isAuthenticated) {
      const response = createResponse({ msg: "Please Authenticate." }, "error");
      ws.send(response.toString());
      return;
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
        zmqLndRequest(JSON.stringify(msg), onZmqReply);
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
            payment_request: d.paymentRequest,
          },
        };
        zmqLndRequest(JSON.stringify(msg), onZmqReply);
      }
    } else if (d.type === GET_NODE_INFO) {
      const msg = {
        action: "get_node_info",
      };
      zmqLndRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === GET_CHANNEL_BALANCES) {
      const msg = {
        action: "get_channel_balances",
      };
      zmqLndRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === GET_WALLET_BALANCES) {
      const msg = {
        action: "get_wallet_balances",
      };
      zmqLndRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === LNURL_AUTH) {
      const msg = {
        action: "lnurl_auth",
        data: { lnurl: d.lnurl },
      };
      zmqLndRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === GET_HEDGE_STATE) {
      const msg = {
        action: "get_hedge_state",
      };
      zmqHedgerRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === GET_WALLET_STATE) {
      const msg = {
        action: "get_wallet_state",
      };
      zmqHedgerRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === CREATE_NEW_HEDGE) {
      const msg = {
        action: "create_new_hedge",
        data: {
          amount: d.amountInSats,
          is_staged: d.isStaged
        },
      };
      zmqHedgerRequest(JSON.stringify(msg), onZmqReply);
    } else if (d.type === LNURL_AUTH_HEDGE) {
      const msg = {
        action: "lnurl_auth_hedge",
        data: {
        },
      };
      zmqLndRequest(JSON.stringify(msg), onZmqReply);
    } else {
      ws.send(createResponse({"msg": "action not available"}, "error"))
    }
  });
});
