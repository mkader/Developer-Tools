 using System;
 using Microsoft.Azure.Cosmos;

 string endpoint = "<cosmos-endpoint>";

 string key = "<cosmos-key>";

 CosmosClient client = new (endpoint, key);

 Database database = await client.CreateDatabaseIfNotExistsAsync("cosmicworks");

 Container container = await database.CreateContainerIfNotExistsAsync("products", "/category/name");

 string sql = "SELECT * FROM products p";
 QueryDefinition query = new (sql);

 using FeedIterator<Product> feed = container.GetItemQueryIterator<Product>(
     queryDefinition: query
 );

 while (feed.HasMoreResults)
 {
     FeedResponse<Product> response = await feed.ReadNextAsync();
     foreach (Product product in response)
     {
         Console.WriteLine($"[{product.id}]\t{product.name,35}\t{product.price,15:C}");
     }
 }
