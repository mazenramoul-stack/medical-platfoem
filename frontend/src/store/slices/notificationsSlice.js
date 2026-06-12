import { createSlice } from '@reduxjs/toolkit';

const notificationsSlice = createSlice({
  name: 'notifications',
  initialState: { items: [] },
  reducers: {
    push: (state, action) => {
      state.items.unshift({ id: Date.now(), ...action.payload });
      if (state.items.length > 50) state.items = state.items.slice(0, 50);
    },
    markRead: (state, action) => {
      const n = state.items.find((i) => i.id === action.payload);
      if (n) n.read = true;
    },
    clear: (state) => { state.items = []; },
  },
});

export const { push, markRead, clear } = notificationsSlice.actions;
export default notificationsSlice.reducer;
