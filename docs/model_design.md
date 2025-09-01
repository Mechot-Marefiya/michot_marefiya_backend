# Database Design

The DB schema is designed to have a separate table for each main category like `Hotels`, `Cars`, `House`

## Requirement Clarification

We might have individuals that need to list their `car` or `condominium` so how do we handle?

**thought** It's obvious that we will not give them a dashboard cause we don't trust every individual
so I'm thinking:

### 1. Michot admin

- Allow michot admin to add such verified individuals properties to listings. To do so,
We need to make two foreign keys (`CompanyProfile`, and `IndividualProfile`) in the listings table. Both should be `blank=true, null=true` but we gonna enforce one of them using `checkConstraint`.
