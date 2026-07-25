import { test, expect } from "@playwright/test";
import { generateTestAccounts } from "../../helpers/test-setup";
import {
  apiLogin,
  apiCreateRoom,
  apiGetRoom,
  apiJoinRoom,
  apiStartGame,
  apiGetUndercoverState,
  apiSubmitDescription,
  apiSubmitVote,
  apiUpdateRoomSettings,
} from "../../helpers/api-client";
import { API_URL } from "../../helpers/constants";

test.describe("Room Rematch", () => {
  test("rematch clears active game and returns to lobby", async () => {
    const accounts = await generateTestAccounts(3);
    const logins = await Promise.all(
      accounts.map((a) => apiLogin(a.email, a.password)),
    );

    // Create room and join all players
    const room = await apiCreateRoom(logins[0].access_token);
    const roomDetails = await apiGetRoom(room.id, logins[0].access_token);

    await apiUpdateRoomSettings(
      room.id,
      { description_timer: 600, voting_timer: 600 },
      logins[0].access_token,
    );

    for (let i = 1; i < logins.length; i++) {
      await apiJoinRoom(
        roomDetails.public_id,
        logins[i].user.id,
        roomDetails.password,
        logins[i].access_token,
      );
    }

    // Start game
    const game = await apiStartGame(room.id, "undercover", logins[0].access_token);

    // Play to completion: describe + vote out players until game ends
    let state = await apiGetUndercoverState(game.game_id, logins[0].access_token);
    let rounds = 0;

    while (!state.winner && rounds < 10) {
      // Submit descriptions
      if (state.turn_phase === "describing" && state.description_order) {
        // Snapshot the order: `state` is reassigned inside the loop, which drops
        // TypeScript's narrowing of state.description_order on the next iteration.
        const describeOrder = state.description_order;
        for (let idx = 0; idx < describeOrder.length; idx++) {
          const describer = describeOrder[idx];
          const login = logins.find((l) => l.user.id === describer.user_id);
          if (login) {
            await apiSubmitDescription(game.game_id, `word${idx}`, login.access_token).catch(() => {});
          }
          // Re-fetch state
          state = await apiGetUndercoverState(game.game_id, logins[0].access_token);
          if (state.turn_phase !== "describing") break;
        }
      }

      // Re-fetch after descriptions
      state = await apiGetUndercoverState(game.game_id, logins[0].access_token);

      // Vote: all alive players vote for first alive non-self player
      if (state.turn_phase === "voting") {
        const alivePlayers = state.players.filter((p) => p.is_alive);
        for (const voter of alivePlayers) {
          const target = alivePlayers.find((p) => p.user_id !== voter.user_id);
          if (!target) continue;
          const login = logins.find((l) => l.user.id === voter.user_id);
          if (login) {
            await apiSubmitVote(game.game_id, target.user_id, login.access_token).catch(() => {});
          }
        }
      }

      // Wait for server to process
      await new Promise((r) => setTimeout(r, 500));
      state = await apiGetUndercoverState(game.game_id, logins[0].access_token);
      rounds++;
    }

    // Call rematch
    const res = await fetch(`${API_URL}/api/v1/rooms/${room.id}/rematch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${logins[0].access_token}`,
      },
    });
    expect(res.status).toBe(200);

    const rematchData = await res.json();
    expect(rematchData).toHaveProperty("room_id", room.id);
    expect(rematchData).toHaveProperty("status", "lobby");
  });
});
