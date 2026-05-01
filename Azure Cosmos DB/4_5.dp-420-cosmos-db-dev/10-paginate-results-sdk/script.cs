 using System;
 using Microsoft.Azure.Cosmos;

 string endpoint = "<cosmos-endpoint>";

 string key = "<cosmos-key>";

 CosmosClient client = new CosmosClient(endpoint, key);

 Database database = await client.CreateDatabaseIfNotExistsAsync("cosmicworks");

 Container container = await database.CreateContainerIfNotExistsAsync("products", "/category/name");

 string sql = "SELECT p.id, p.name, p.price FROM products p ";
 QueryDefinition query = new (sql);

 QueryRequestOptions options = new ();
 options.MaxItemCount = 50;

 FeedIterator<Product> iterator = container.GetItemQueryIterator<Product>(query, requestOptions: options);

 while (iterator.HasMoreResults)
 {
     FeedResponse<Product> products = await iterator.ReadNextAsync();
     foreach (Product product in products)
     {
         Console.WriteLine($"[{product.id}]\t[{product.name,40}]\t[{product.price,10}]");
     }

     Console.WriteLine("Press any key for next page of results");
     Console.ReadKey();        
 }
