"""Hashnode platform implementation using GraphQL API."""

from typing import Any

from .base import Article, DeleteResult, Platform, PublishResult


class Hashnode(Platform):
    """Hashnode publishing platform.

    Requires a Hashnode Personal Access Token.
    Get yours at: https://hashnode.com/settings/developer

    api_key format: "token" or "token:publication_id"
    If publication_id not provided, will use primary publication.
    """

    name = "hashnode"
    description = "Developer blogging platform"
    base_url = "https://gql.hashnode.com"
    api_key_url = "https://hashnode.com/settings/developer"

    def __init__(self, api_key: str, publication_id: str | None = None):
        super().__init__(api_key)

        if ":" in api_key and publication_id is None:
            self.token, self.publication_id = api_key.split(":", 1)
        else:
            self.token = api_key
            self.publication_id = publication_id

        self.headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    def _graphql(self, query: str, variables: dict | None = None) -> dict[str, Any]:
        """Execute a GraphQL query."""
        resp = self.retry_request(
            "post",
            self.base_url,
            headers=self.headers,
            json={"query": query, "variables": variables or {}},
        )

        if resp.status_code == 200:
            return resp.json()
        return {"errors": [{"message": f"{resp.status_code}: {resp.text}"}]}

    def _get_publication_id(self) -> str | None:
        """Get the user's publication ID if not configured."""
        if self.publication_id:
            return self.publication_id

        query = """
        query {
            me {
                publications(first: 1) {
                    edges {
                        node {
                            id
                        }
                    }
                }
            }
        }
        """

        result = self._graphql(query)
        pubs = result.get("data", {}).get("me", {}).get("publications", {}).get("edges", [])
        if pubs:
            self.publication_id = pubs[0]["node"]["id"]
            return self.publication_id
        return None

    def publish(self, article: Article) -> PublishResult:
        """Publish an article to Hashnode."""
        pub_id = self._get_publication_id()
        if not pub_id:
            return PublishResult(
                success=False,
                platform=self.name,
                error="No publication found. Create one at hashnode.com first.",
            )

        # Generate slug from title
        slug = article.title.lower()
        slug = "".join(c if c.isalnum() or c == " " else "" for c in slug)
        slug = "-".join(slug.split())[:100]

        # Use publishPost mutation (new API)
        query = """
        mutation PublishPost($input: PublishPostInput!) {
            publishPost(input: $input) {
                post {
                    id
                    url
                    slug
                }
            }
        }
        """

        variables = {
            "input": {
                "publicationId": pub_id,
                "title": article.title,
                "contentMarkdown": article.body,
                "slug": slug,
            }
        }

        if article.tags:
            # Hashnode uses tag slugs
            variables["input"]["tags"] = [{"slug": tag.lower().replace(" ", "-"), "name": tag} for tag in article.tags[:5]]

        if article.canonical_url:
            variables["input"]["originalArticleURL"] = article.canonical_url

        if article.description:
            variables["input"]["subtitle"] = article.description[:150]

        result = self._graphql(query, variables)

        if "errors" in result:
            error_msg = result["errors"][0].get("message", "Unknown error")
            return PublishResult(
                success=False,
                platform=self.name,
                error=error_msg,
            )

        post = result.get("data", {}).get("publishPost", {}).get("post", {})
        return PublishResult(
            success=True,
            platform=self.name,
            article_id=post.get("id"),
            url=post.get("url"),
        )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Update an existing article on Hashnode."""
        query = """
        mutation UpdatePost($input: UpdatePostInput!) {
            updatePost(input: $input) {
                post {
                    id
                    url
                }
            }
        }
        """

        variables = {
            "input": {
                "id": article_id,
                "title": article.title,
                "contentMarkdown": article.body,
            }
        }

        if article.description:
            variables["input"]["subtitle"] = article.description[:150]

        result = self._graphql(query, variables)

        if "errors" in result:
            error_msg = result["errors"][0].get("message", "Unknown error")
            return PublishResult(
                success=False,
                platform=self.name,
                error=error_msg,
            )

        post = result.get("data", {}).get("updatePost", {}).get("post", {})
        return PublishResult(
            success=True,
            platform=self.name,
            article_id=post.get("id"),
            url=post.get("url"),
        )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        """List your articles on Hashnode."""
        pub_id = self._get_publication_id()
        if not pub_id:
            return []

        query = """
        query GetPosts($publicationId: ObjectId!, $first: Int!) {
            publication(id: $publicationId) {
                posts(first: $first) {
                    edges {
                        node {
                            id
                            title
                            url
                            publishedAt
                        }
                    }
                }
            }
        }
        """

        result = self._graphql(query, {"publicationId": pub_id, "first": limit})
        posts = result.get("data", {}).get("publication", {}).get("posts", {}).get("edges", [])

        return [
            {
                "id": post["node"]["id"],
                "title": post["node"]["title"][:50],
                "published": True,
                "url": post["node"]["url"],
            }
            for post in posts
        ]

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        """Get a specific article by ID."""
        query = """
        query GetPost($id: ID!) {
            post(id: $id) {
                id
                title
                content { markdown }
                url
            }
        }
        """

        result = self._graphql(query, {"id": article_id})
        return result.get("data", {}).get("post")

    def delete(self, article_id: str) -> DeleteResult:
        """Delete an article."""
        query = """
        mutation RemovePost($id: ID!) {
            removePost(id: $id) {
                post { id }
            }
        }
        """

        result = self._graphql(query, {"id": article_id})
        if "errors" not in result:
            return DeleteResult(success=True, platform=self.name)
        error_msg = result["errors"][0].get("message", "Unknown error")
        return DeleteResult(success=False, platform=self.name, error=error_msg)
