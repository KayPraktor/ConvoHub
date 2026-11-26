# ConvoHub browser extension

فارسی: [docs/fa/EXTENSION.md](fa/EXTENSION.md)

With this extension, the chat you have open in your own browser (Gemini, ChatGPT, Claude, Grok) goes into your ConvoHub library with one click. After that, whenever that chat is open and new messages arrive, they are added automatically.

- The extension reads only **the text of the page in front of you**. It doesn't touch cookies, passwords or these sites' servers.
- It works only with the **web** versions of these sites, not their desktop apps.
- ConvoHub has to be running.
- The extension shows its buttons and messages in the same language as the ConvoHub app (English or Persian). If ConvoHub has never been reached, it uses your browser's language.

## Install (Chrome or Edge)

The easiest way: in ConvoHub, click **Connect** at the bottom of the sidebar. The same steps are there, with the right folder path for your computer and an **Open folder** button.

1. **Find the extension folder:**
   - **Installed version (Setup.exe):** `%LOCALAPPDATA%\Programs\ConvoHub\extension`
   - **Source version:** the `extension` folder inside the project folder
2. In Chrome, go to `chrome://extensions` (in Edge: `edge://extensions`).
3. Turn on **Developer mode**.
4. Click **Load unpacked** and pick the extension folder.
5. Open or refresh a chat page. In ConvoHub, above the library, a bar saying **"An extension wants to connect"** appears. Click **Accept**.
   - Every installed copy of the extension has its own ID, and ConvoHub accepts only an extension you approved.
   - If the bar doesn't appear, copy the ID from the extension's card in `chrome://extensions` and paste it under **Agent** → the "Browser extension" section.

Chrome may sometimes suggest "Turn off extensions in developer mode". It shows this for every extension that didn't come from the Web Store; ignore it.

## Use

- **Send a chat:** open the chat page. A **"Send to ConvoHub"** button appears at the bottom right (sometimes a few seconds after the page opens). Click it. The extension first scrolls up to the start of the conversation so older messages load too, then sends all of them.
- **Automatic sync:** for chats you have sent once, new messages are added automatically after each answer finishes.
  - You can turn this on or off in the extension's settings.
  - Automatic sync never deletes or replaces anything. If it can't match the new messages with the earlier ones, the button asks you to click once.

## Taking a conversation back to a chat (handoff)

When you have continued a conversation in ConvoHub and want to go back to the same Gemini chat (or take it to another chatbot):

1. In the ConvoHub conversation, click **Continue elsewhere** at the top of the page, choose the destination and click **Send to extension**.
2. Open (or refresh) the destination chat in your browser. Above the usual button, a **"Put the ConvoHub text in the message box"** button appears.
3. Click it. The text is placed in the message box. Look it over and press Send **yourself**. The extension never sends a message on its own.

- The text waits for up to 15 minutes and can be taken only once.
- If no message box is found, the text is copied so you can paste it with Ctrl+V.
- When that chat is later synced with ConvoHub again, the handoff text isn't stored in full; only its first line is kept, because the original is already in ConvoHub.

## If it doesn't work

- **"ConvoHub isn't running":** open ConvoHub.
- **"Click Accept in ConvoHub":** see step 5 above.
- **"No messages found":** the site has probably changed the structure of its page. The extension saves a report of the page **structure** (without the message text) in ConvoHub's data folder: `extension-diagnose.json`. You can open an Issue on GitHub and attach that file.
- **After updating ConvoHub:** click the extension's reload button in `chrome://extensions` and refresh the chat page.
