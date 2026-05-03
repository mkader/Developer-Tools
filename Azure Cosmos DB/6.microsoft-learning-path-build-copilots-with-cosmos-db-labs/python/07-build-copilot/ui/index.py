import streamlit as st
import requests

st.set_page_config(page_title="Cosmic Works Copilot", layout="wide")

async def send_message_to_copilot(message: str, chat_history: list = []) -> str:
    """Send a message to the Copilot chat endpoint."""
    try:
        api_endpoint = "http://localhost:8000"
        request = {"message": message, "chat_history": chat_history}
        response = requests.post(f"{api_endpoint}/chat", json=request, timeout=60)
        return response.json()
    except Exception as e:
        st.error(f"An error occurred: {e}")
        return""

async def main():
    """Main function for the Cosmic Works Product Management Copilot UI."""
    
    st.write(
        """
        # Cosmic Works Product Management Copilot
        
        Welcome to Cosmic Works Product Management Copilot, a tool for managing and finding bicycle-related products in the Cosmic Works system.
        
        **Ask the copilot to apply or remove a discount on a category of products or to find products.**
        """
    )
    
    # Add a messages collection to the session state to maintain the chat history.
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Display message from the history on app rerun.
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # React to user input
    if prompt := st.chat_input("What can I help you with today?"):
        with st. spinner("Awaiting the copilot's response to your message..."):
            # Display user message in chat message container
            with st.chat_message("user"):
                st.markdown(prompt)
                
            # Send the user message to the copilot API
            response = await send_message_to_copilot(prompt, st.session_state.messages)
    
            # Display assistant response in chat message container
            with st.chat_message("assistant"):
                st.markdown(response)
                
            # Add the current user message and assistant response messages to the chat history
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.session_state.messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())