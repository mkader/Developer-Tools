from openai import AsyncAzureOpenAI
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
from azure.cosmos.aio import CosmosClient
from models import Product, CompletionRequest
from contextlib import asynccontextmanager
from fastapi import FastAPI
import json
    
# Azure OpenAI configuration
AZURE_OPENAI_ENDPOINT = "https://maoai.openai.azure.com/"
AZURE_OPENAI_API_VERSION = "2024-10-21"
EMBEDDING_DEPLOYMENT_NAME = "text-embedding-3-small"
COMPLETION_DEPLOYMENT_NAME = 'gpt-4o'

# Azure Cosmos DB configuration
AZURE_COSMOSDB_CONNECTION_STRING = "AccountEndpoint=https://cosmicworks.documents.azure.com:443/;AccountKey=P...9EA==;"
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
    # Provide the copilot with a persona using the system prompt.
    messages = [{ "role": "system", "content": system_prompt }]
    print("M1 : =>",messages)

    # Add the chat history to the messages list
    for message in request.chat_history[-request.max_history:]:
        messages.append(message)

    # Add the current user message to the messages list
    messages.append({"role": "user", "content": request.message})

    print("M2 : =>",messages)

    # Define function calling tools
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_similar_products",
                "description": "Retrieve similar products based on a user message.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "The user's message looking for similar products"},
                        "num_results": {"type": "integer", "description": "The number of similar products to return"}
                    },
                    "required": ["message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "apply_discount",
                "description": "Apply a discount to products in the specified category",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "discount": {"type": "number", "description": "The percent discount to apply."},
                        "product_category": {"type": "string", "description": "The category of products to which the discount should be applied."}
                    },
                    "required": ["discount", "product_category"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_category_names",
                "description": "Retrieves the names of all product categories"
            }
        }
    ]
    # Create Azure OpenAI client
    aoai_client = AsyncAzureOpenAI(
        api_version = AZURE_OPENAI_API_VERSION,
        azure_endpoint = AZURE_OPENAI_ENDPOINT,
        azure_ad_token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    )

    # First API call, providing the model to the defined functions
    response = await aoai_client.chat.completions.create(
        model = COMPLETION_DEPLOYMENT_NAME,
        messages = messages,
        tools = tools,
        tool_choice = "auto"
    )

    print("R3 => ", response)

    # Process the model's response
    response_message = response.choices[0].message
    messages.append(response_message)

    print("M4 => ", messages)

    # Handle function call outputs
    if response_message.tool_calls:
        for call in response_message.tool_calls:
            if call.function.name == "apply_discount":
                func_response = await apply_discount(**json.loads(call.function.arguments))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "content": func_response
                    }
                )
            elif call.function.name == "get_category_names":
                func_response = await get_category_names()
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "content": json.dumps(func_response)
                    }
                )
            elif call.function.name == "get_similar_products":
                func_response = await get_similar_products(**json.loads(call.function.arguments))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.function.name,
                        "content": json.dumps(func_response)
                    }
                )
    else:
        print("No function calls were made by the model.")

    print("M5 => ", messages)

    # Second API call, asking the model to generate a response
    final_response = await aoai_client.chat.completions.create(
        model = COMPLETION_DEPLOYMENT_NAME,
        messages = messages
    )

    print("R6 => ", final_response)
    return final_response.choices[0].message.content
    
async def generate_embeddings(text: str):
    # Create Azure OpenAI client
    async with AsyncAzureOpenAI(
        api_version = AZURE_OPENAI_API_VERSION,
        azure_endpoint = AZURE_OPENAI_ENDPOINT,
        azure_ad_token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    ) as client:
        response = await client.embeddings.create(
            input = text,
            model = EMBEDDING_DEPLOYMENT_NAME
        )
        return response.data[0].embedding
    
async def upsert_product(product: Product):
    """Upserts the provided product to the Cosmos DB container."""
    # Create an async Cosmos DB client
    async with CosmosClient(url=AZURE_COSMOSDB_ENDPOINT, credential=credential) as client:
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