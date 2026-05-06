from langchain_openai import AzureOpenAIEmbeddings
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from azure.cosmos.aio import CosmosClient
from models import Product, CompletionRequest
from contextlib import asynccontextmanager
from fastapi import FastAPI
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool

# Azure OpenAI configuration
AZURE_OPENAI_ENDPOINT = "https://maoai.openai.azure.com/"
AZURE_OPENAI_API_VERSION = "2024-10-21"
EMBEDDING_DEPLOYMENT_NAME = "text-embedding-3-small"
COMPLETION_DEPLOYMENT_NAME = 'gpt-4o'

# Azure Cosmos DB configuration
AZURE_COSMOSDB_CONNECTION_STRING = "AccountEndpoint=https://cosmicworks.documents.azure.com:443/;AccountKey=PZ...9EA==;"
DATABASE_NAME = "CosmicWorks"
CONTAINER_NAME = "Products"
    
# Create a global async Cosmos DB client
cosmos_client = None
# Create a global async Microsoft Entra ID RBAC credential
credential = None
   
@asynccontextmanager
async def lifespan(app: FastAPI):
    global cosmos_client
    global credential
    # Create an async Microsoft Entra ID RBAC credential
    credential = DefaultAzureCredential()
    # Create an async Cosmos DB client using Microsoft Entra ID RBAC authentication
    cosmos_client = CosmosClient.from_connection_string(AZURE_COSMOSDB_CONNECTION_STRING)
    yield
    await cosmos_client.close()
    await credential.close()

app = FastAPI(lifespan=lifespan)
    
@app.get("/")
async def api_status():
    return {"status": "ready"}
 
@app.post('/chat')
async def generate_chat_completion(request: CompletionRequest):
    """Generate a chat completion using the Azure OpenAI API."""
    # Define the system prompt that contains the assistant's persona.
    system_prompt = """
    You are an intelligent copilot for Cosmic Works designed to help users manage and find bicycle-related products.
    You are helpful, friendly, and knowledgeable, but can only answer questions about Cosmic Works products.
    If asked to apply a discount:
        - Apply the specified discount to all products in the specified category. If the user did not provide you with a discount percentage and a product category, prompt them for the details you need to apply a discount.
        - Discount amounts should be specified as a decimal value (e.g., 0.1 for 10% off).
    If asked to remove discounts from a category:
        - Remove any discounts applied to products in the specified category by setting the discount value to 0.
    When asked to provide a list of products, you should:
        - Provide at least 3 candidate products unless the user asks for more or less, then use that number. Always include each product's name, description, price, and SKU. If the product has a discount, include it as a percentage and the associated sale price.
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder("chat_history", optional=True),
            ("user", "{input}"),
            MessagesPlaceholder("agent_scratchpad")
        ]
    )
    
    # Define function calling tools
    tools = [
        StructuredTool.from_function(apply_discount),
        StructuredTool.from_function(get_category_names),
        StructuredTool.from_function(get_similar_products)
    ]
    
    # Connect to Azure OpenAI API
    azure_openai = AzureChatOpenAI(
        azure_deployment=COMPLETION_DEPLOYMENT_NAME,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        azure_ad_token_provider=get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default"),
        api_version=AZURE_OPENAI_API_VERSION
    )
    
    agent = create_openai_functions_agent(llm=azure_openai, tools=tools, prompt=prompt)
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, return_intermediate_steps=True)
        
    completion = await agent_executor.ainvoke({"input": request.message, "chat_history": request.chat_history[-request.max_history:]})

    print(completion)
            
    return completion["output"]

async def generate_embeddings(text: str):
    """Generates embeddings for the provided text."""
    # Use LangChain's Azure OpenAI Embeddings class
    azure_openai_embeddings = AzureOpenAIEmbeddings(
        azure_deployment = EMBEDDING_DEPLOYMENT_NAME,
        azure_endpoint = AZURE_OPENAI_ENDPOINT,
        azure_ad_token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    )
    return await azure_openai_embeddings.aembed_query(text)
    
async def upsert_product(product: Product):
    """Upserts the provided product to the Cosmos DB container."""
    # Create an async Cosmos DB client
    async with CosmosClient.CosmosClient.from_connection_string(AZURE_COSMOSDB_CONNECTION_STRING) as client:
        # Load the CosmicWorks database
        database = client.get_database_client(DATABASE_NAME)
        # Retrieve the product container
        container = database.get_container_client(CONTAINER_NAME)
        # Upsert the product
        await container.upsert_item(product)

async def apply_discount(discount: float, product_category: str) -> str:
    """Apply a discount to products in the specified category."""
    # Load the CosmicWorks database
    database = cosmos_client.get_database_client(DATABASE_NAME)
    # Retrieve the product container
    container = database.get_container_client(CONTAINER_NAME)
    
    query_results = container.query_items(
        query = """
        SELECT * FROM Products p WHERE CONTAINS(LOWER(p.category_name), LOWER(@product_category))
        """,
        parameters = [
            {"name": "@product_category", "value": product_category}
        ]
    )
    
    # Apply the discount to the products
    async for item in query_results:
        item['discount'] = discount
        item['sale_price'] = item['price'] * (1 - discount) if discount > 0 else item['price']
        await container.upsert_item(item)
    
    return f"A {discount}% discount was successfully applied to {product_category}." if discount > 0 else f"Discounts on {product_category} removed successfully."

async def get_category_names() -> list:
    """Retrieve the names of all product categories."""
    # Load the CosmicWorks database
    database = cosmos_client.get_database_client(DATABASE_NAME)
    # Retrieve the product container
    container = database.get_container_client(CONTAINER_NAME)
    # Get distinct product categories
    query_results = container.query_items(
        query = "SELECT DISTINCT VALUE p.category_name FROM Products p"
    )
    categories = []
    async for category in query_results:
        categories.append(category)
    return list(categories)

async def vector_search(query_embedding: list, num_results: int = 3, similarity_score: float = 0.25):
    """Search for similar product vectors in Azure Cosmos DB"""
    # Load the CosmicWorks database
    database = cosmos_client.get_database_client(DATABASE_NAME)
    # Retrieve the product container
    container = database.get_container_client(CONTAINER_NAME)
    
    query_results = container.query_items(
        query = """
        SELECT TOP @num_results p.name, p.description, p.sku, p.price, p.discount, p.sale_price, VectorDistance(p.embedding, @query_embedding) AS similarity_score
        FROM Products p
        WHERE VectorDistance(p.embedding, @query_embedding) > @similarity_score
        ORDER BY VectorDistance(p.embedding, @query_embedding)
        """,
        parameters = [
            {"name": "@query_embedding", "value": query_embedding},
            {"name": "@num_results", "value": num_results},
            {"name": "@similarity_score", "value": similarity_score}
        ]
    )
    similar_products = []
    async for result in query_results:
        similar_products.append(result)
    formatted_results = [{'similarity_score': product.pop('similarity_score'), 'product': product} for product in similar_products]
    return formatted_results

async def get_similar_products(message: str, num_results: int):
    """Retrieve similar products based on a user message."""
    # Vectorize the message
    embedding = await generate_embeddings(message)
    # Perform vector search against products in Cosmos DB
    similar_products = await vector_search(embedding, num_results=num_results)
    return similar_products
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
