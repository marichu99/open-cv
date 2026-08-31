import { io, type Socket } from "socket.io-client";
import { SOCKET_URL } from "./api";

let socket: Socket | null = null;

/** Lazily connects a single shared socket to the tally_updated channel. */
export function getSocket(): Socket {
  if (!socket) {
    socket = io(SOCKET_URL, { transports: ["websocket"], autoConnect: true });
  }
  return socket;
}
